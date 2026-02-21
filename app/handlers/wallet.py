from __future__ import annotations

import json
from math import ceil
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from telebot import TeleBot, types
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, PreCheckoutQuery

from ..callbacks import Cb, pack, unpack
from ..keyboards import wallet_kb
from ..states import WalletStates
from ..storage import (
    complete_topup_payment,
    create_topup_payment,
    get_topup_payment,
    get_topup_payment_by_payload,
    get_user,
    list_balance_events,
)
from ..utils import edit_message_any, format_display_datetime


_WALLET_CTX: dict[tuple[int, int], dict[str, Any]] = {}


def _ctx_key(user_id: int, chat_id: int) -> tuple[int, int]:
    return int(user_id), int(chat_id)


def _ctx_set(user_id: int, chat_id: int, **kwargs) -> None:
    key = _ctx_key(user_id, chat_id)
    d = _WALLET_CTX.get(key) or {}
    d.update(kwargs)
    _WALLET_CTX[key] = d


def _ctx_get(user_id: int, chat_id: int) -> dict[str, Any]:
    return _WALLET_CTX.get(_ctx_key(user_id, chat_id), {})


def _ctx_clear(user_id: int, chat_id: int) -> None:
    _WALLET_CTX.pop(_ctx_key(user_id, chat_id), None)


def _wallet_text(user_id: int, username: str | None) -> str:
    u = get_user(user_id, username)
    return (
        "💰 Кошелёк\n"
        f"Текущий баланс: {u.balance}\n\n"
        "Выберите действие:"
    )


def _history_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("⬅️ К кошельку", callback_data=pack(Cb.NAV, "wallet")))
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _wallet_result_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("💰 Кошелёк", callback_data=pack(Cb.NAV, "wallet")))
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _topup_method_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🤖 CryptoBot", callback_data=pack(Cb.WAL, "method", "cryptobot")))
    kb.add(InlineKeyboardButton("⭐ Звёзды", callback_data=pack(Cb.WAL, "method", "stars")))
    kb.add(InlineKeyboardButton("💳 YooMoney", callback_data=pack(Cb.WAL, "method", "yoomoney")))
    kb.add(InlineKeyboardButton("⬅️ К кошельку", callback_data=pack(Cb.NAV, "wallet")))
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _payment_link_kb(url: str, method: str, payment_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("💳 Оплатить", url=url))
    kb.add(InlineKeyboardButton("🔄 Проверить оплату", callback_data=pack(Cb.WAL, "check", method, str(payment_id))))
    kb.add(InlineKeyboardButton("💰 Кошелёк", callback_data=pack(Cb.NAV, "wallet")))
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _calc_stars_amount(balance_amount: int, balance_per_star: int) -> int:
    rate = max(1, int(balance_per_star))
    return max(1, int(ceil(int(balance_amount) / rate)))


def _http_json(method: str, url: str, *, headers: dict[str, str] | None = None, payload: dict | None = None) -> dict:
    body = None
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"

    req = Request(url=url, method=method.upper(), headers=hdrs, data=body)
    with urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def _cryptobot_create_invoice(api_token: str, amount_rub: int, payload: str) -> tuple[bool, str, str]:
    if not api_token:
        return False, "", "Не заполнен CRYPTO_BOT_API_TOKEN в .env"

    url = "https://pay.crypt.bot/api/createInvoice"
    data = {
        "currency_type": "fiat",
        "fiat": "RUB",
        "amount": str(int(amount_rub)),
        "description": f"Пополнение баланса на {int(amount_rub)}",
        "payload": payload,
    }
    try:
        res = _http_json("POST", url, headers={"Crypto-Pay-API-Token": api_token}, payload=data)
    except Exception:
        return False, "", "Ошибка подключения к CryptoBot API"

    if not bool(res.get("ok")):
        return False, "", f"CryptoBot API вернул ошибку: {res.get('error', {}).get('name', 'unknown')}"

    result = res.get("result") or {}
    invoice_id = str(result.get("invoice_id") or "").strip()
    pay_url = str(result.get("mini_app_invoice_url") or result.get("pay_url") or result.get("bot_invoice_url") or "").strip()
    if not invoice_id or not pay_url:
        return False, "", "CryptoBot API вернул неполный ответ"

    return True, invoice_id, pay_url


def _cryptobot_is_paid(api_token: str, invoice_id: str) -> tuple[bool, str]:
    if not api_token:
        return False, "Не заполнен CRYPTO_BOT_API_TOKEN"
    if not invoice_id:
        return False, "Не найден invoice_id"

    url = f"https://pay.crypt.bot/api/getInvoices?invoice_ids={invoice_id}"
    try:
        res = _http_json("GET", url, headers={"Crypto-Pay-API-Token": api_token})
    except Exception:
        return False, "Ошибка подключения к CryptoBot API"

    if not bool(res.get("ok")):
        return False, "Ошибка ответа CryptoBot API"

    items = ((res.get("result") or {}).get("items") or [])
    if not items:
        return False, "Счет не найден в CryptoBot"

    status = str((items[0] or {}).get("status") or "").lower().strip()
    if status == "paid":
        return True, "paid"
    if status:
        return False, f"Статус счета: {status}"
    return False, "Неизвестный статус счета"


def _yoomoney_payment_link(receiver: str, amount: int, label: str, payment_type: str) -> str:
    base = "https://yoomoney.ru/quickpay/confirm.xml"
    params = {
        "receiver": receiver,
        "quickpay-form": "shop",
        "targets": "Пополнение баланса",
        "paymentType": payment_type,
        "sum": str(int(amount)),
        "label": label,
    }
    return f"{base}?{urlencode(params)}"


def _yoomoney_is_paid(oauth_token: str, label: str, expected_amount: int) -> tuple[bool, str]:
    if not oauth_token:
        return False, "Не заполнен YOOMONEY_OAUTH_TOKEN"

    url = "https://yoomoney.ru/api/operation-history"
    form = urlencode({"label": label, "records": 30}).encode("utf-8")
    req = Request(
        url=url,
        method="POST",
        data=form,
        headers={
            "Authorization": f"Bearer {oauth_token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
    except Exception:
        return False, "Ошибка запроса к YooMoney API"

    ops = data.get("operations") or []
    for op in ops:
        if str(op.get("label") or "") != label:
            continue
        status = str(op.get("status") or "").lower().strip()
        amount = int(float(op.get("amount") or 0))
        if status == "success" and amount >= int(expected_amount):
            return True, "paid"
    return False, "Оплата пока не найдена"


def register(bot: TeleBot):
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.NAV + ":wallet"))
    def open_wallet(c: CallbackQuery):
        try:
            edit_message_any(
                bot,
                c.message,
                _wallet_text(c.from_user.id, c.from_user.username),
                reply_markup=wallet_kb(),
            )
        finally:
            bot.answer_callback_query(c.id)

    @bot.callback_query_handler(func=lambda c: c.data and c.data == pack(Cb.WAL, "topup"))
    def wallet_topup(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        _ctx_clear(c.from_user.id, c.message.chat.id)
        bot.send_message(c.message.chat.id, "Выберите способ пополнения:", reply_markup=_topup_method_kb())

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.WAL + ":method:"))
    def wallet_topup_method(c: CallbackQuery):
        parts = unpack(c.data)
        method = (parts[2] if len(parts) > 2 else "").strip().lower()
        if method not in ("cryptobot", "stars", "yoomoney"):
            bot.answer_callback_query(c.id, "Неизвестный способ оплаты")
            return

        bot.answer_callback_query(c.id)
        _ctx_set(c.from_user.id, c.message.chat.id, topup_method=method)

        cfg = getattr(bot, "_cfg", None)
        if method == "stars":
            rate = max(1, int(getattr(cfg, "topup_balance_per_star", 2) or 2))
            text = (
                "⭐ Пополнение через Telegram Stars\n"
                "Введите сумму пополнения (целое число).\n"
                f"Текущий курс: 1 XTR = {rate} баланса."
            )
        elif method == "cryptobot":
            text = (
                "🤖 Пополнение через CryptoBot\n"
                "Введите сумму пополнения в рублях (целое число).\n"
                "К зачислению будет 1:1."
            )
        else:
            text = (
                "💳 Пополнение через YooMoney\n"
                "Введите сумму пополнения в рублях (целое число).\n"
                "К зачислению будет 1:1."
            )

        bot.send_message(c.message.chat.id, text, reply_markup=_history_kb())
        bot.set_state(c.from_user.id, WalletStates.topup_amount, c.message.chat.id)

    @bot.message_handler(state=WalletStates.topup_amount, content_types=["text"])
    def wallet_topup_amount(m: Message):
        raw = (m.text or "").strip()
        if not raw.isdigit():
            bot.send_message(m.chat.id, "Сумма должна быть положительным числом.")
            return

        amount = int(raw)
        if amount <= 0:
            bot.send_message(m.chat.id, "Сумма должна быть больше нуля.")
            return
        if amount > 1_000_000_000:
            bot.send_message(m.chat.id, "Слишком большая сумма. Укажите сумму до 1 000 000 000.")
            return

        data = _ctx_get(m.from_user.id, m.chat.id)
        method = str(data.get("topup_method") or "").strip().lower()
        if method not in ("cryptobot", "stars", "yoomoney"):
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            bot.send_message(m.chat.id, "Сессия пополнения потеряна. Нажмите «Пополнить» еще раз.", reply_markup=_wallet_result_kb())
            return

        cfg = getattr(bot, "_cfg", None)
        payload = f"topup:{m.from_user.id}:{uuid4().hex}:{amount}:{method}"

        if method == "stars":
            stars_amount = _calc_stars_amount(amount, int(getattr(cfg, "topup_balance_per_star", 2) or 2))
            try:
                create_topup_payment(
                    user_id=m.from_user.id,
                    amount=amount,
                    stars_amount=stars_amount,
                    payload=payload,
                    payment_method="stars",
                )
            except Exception:
                bot.send_message(m.chat.id, "Не удалось создать счет на пополнение. Попробуйте позже.", reply_markup=_wallet_result_kb())
                bot.delete_state(m.from_user.id, m.chat.id)
                _ctx_clear(m.from_user.id, m.chat.id)
                return

            provider_token = str(getattr(cfg, "stars_provider_token", "") or "").strip() or None
            prices = [types.LabeledPrice(label="XTR", amount=stars_amount)]
            try:
                bot.send_invoice(
                    chat_id=m.chat.id,
                    title="Пополнение баланса",
                    description=f"Пополнение баланса на {amount}",
                    invoice_payload=payload,
                    provider_token=provider_token,
                    currency="XTR",
                    prices=prices,
                )
                bot.send_message(
                    m.chat.id,
                    f"Счет выставлен.\nСумма к оплате: {stars_amount} XTR.\nПосле успешной оплаты баланс зачислится автоматически.",
                    reply_markup=_wallet_result_kb(),
                )
            except Exception:
                bot.send_message(
                    m.chat.id,
                    "Не удалось отправить счет Stars. Проверьте STARS_PROVIDER_TOKEN и попробуйте еще раз.",
                    reply_markup=_wallet_result_kb(),
                )
            finally:
                bot.delete_state(m.from_user.id, m.chat.id)
                _ctx_clear(m.from_user.id, m.chat.id)
            return

        if method == "cryptobot":
            ok, invoice_id, result = _cryptobot_create_invoice(
                str(getattr(cfg, "crypto_bot_api_token", "") or "").strip(),
                amount,
                payload,
            )
            if not ok:
                bot.send_message(m.chat.id, f"Не удалось создать счет CryptoBot: {result}", reply_markup=_wallet_result_kb())
                bot.delete_state(m.from_user.id, m.chat.id)
                _ctx_clear(m.from_user.id, m.chat.id)
                return

            try:
                payment_id = create_topup_payment(
                    user_id=m.from_user.id,
                    amount=amount,
                    stars_amount=0,
                    payload=payload,
                    payment_method="cryptobot",
                    external_payment_id=invoice_id,
                )
            except Exception:
                bot.send_message(m.chat.id, "Не удалось сохранить счет CryptoBot. Попробуйте еще раз.", reply_markup=_wallet_result_kb())
                bot.delete_state(m.from_user.id, m.chat.id)
                _ctx_clear(m.from_user.id, m.chat.id)
                return

            bot.send_message(
                m.chat.id,
                f"Счет CryptoBot создан на {amount} RUB. После оплаты нажмите «Проверить оплату».",
                reply_markup=_payment_link_kb(result, "cryptobot", payment_id),
            )
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            return

        # yoomoney
        wallet = str(getattr(cfg, "yoomoney_wallet", "") or "").strip()
        if not wallet:
            bot.send_message(m.chat.id, "Не заполнен YOOMONEY_WALLET в .env", reply_markup=_wallet_result_kb())
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            return

        label = payload
        pay_url = _yoomoney_payment_link(wallet, amount, label, str(getattr(cfg, "yoomoney_payment_type", "SB") or "SB"))

        try:
            payment_id = create_topup_payment(
                user_id=m.from_user.id,
                amount=amount,
                stars_amount=0,
                payload=payload,
                payment_method="yoomoney",
                external_payment_id=label,
            )
        except Exception:
            bot.send_message(m.chat.id, "Не удалось сохранить счет YooMoney. Попробуйте позже.", reply_markup=_wallet_result_kb())
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            return

        bot.send_message(
            m.chat.id,
            f"Счет YooMoney создан на {amount} RUB. После оплаты нажмите «Проверить оплату».",
            reply_markup=_payment_link_kb(pay_url, "yoomoney", payment_id),
        )
        bot.delete_state(m.from_user.id, m.chat.id)
        _ctx_clear(m.from_user.id, m.chat.id)

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.WAL + ":check:"))
    def wallet_check_payment(c: CallbackQuery):
        parts = unpack(c.data)
        method = (parts[2] if len(parts) > 2 else "").strip().lower()
        pid_raw = (parts[3] if len(parts) > 3 else "").strip()
        if method not in ("cryptobot", "yoomoney") or not pid_raw.isdigit():
            bot.answer_callback_query(c.id, "Некорректные данные", show_alert=True)
            return

        payment = get_topup_payment(int(pid_raw))
        if not payment:
            bot.answer_callback_query(c.id, "Платеж не найден", show_alert=True)
            return
        if int(payment.get("user_id") or 0) != int(c.from_user.id):
            bot.answer_callback_query(c.id, "Это не ваш платеж", show_alert=True)
            return
        if str(payment.get("status") or "") == "paid":
            u = get_user(c.from_user.id, c.from_user.username)
            bot.answer_callback_query(c.id, "Уже оплачен")
            bot.send_message(c.message.chat.id, f"✅ Платеж уже зачислен. Текущий баланс: {u.balance}", reply_markup=_wallet_result_kb())
            return
        if str(payment.get("status") or "") != "pending":
            bot.answer_callback_query(c.id, f"Статус: {payment.get('status')}", show_alert=True)
            return

        cfg = getattr(bot, "_cfg", None)
        paid = False
        info = ""
        if method == "cryptobot":
            paid, info = _cryptobot_is_paid(
                str(getattr(cfg, "crypto_bot_api_token", "") or "").strip(),
                str(payment.get("external_payment_id") or "").strip(),
            )
        else:
            paid, info = _yoomoney_is_paid(
                str(getattr(cfg, "yoomoney_oauth_token", "") or "").strip(),
                str(payment.get("external_payment_id") or "").strip(),
                int(payment.get("amount") or 0),
            )

        if not paid:
            bot.answer_callback_query(c.id, "Платеж пока не найден")
            bot.send_message(c.message.chat.id, f"⏳ Оплата пока не подтверждена. {info}", reply_markup=_wallet_result_kb())
            return

        ok, reason = complete_topup_payment(payload=str(payment.get("payload") or ""))
        if ok:
            u = get_user(c.from_user.id, c.from_user.username)
            bot.answer_callback_query(c.id, "Оплата подтверждена")
            bot.send_message(
                c.message.chat.id,
                f"✅ Пополнение успешно.\nЗачислено: +{int(payment.get('amount') or 0)}\nТекущий баланс: {u.balance}",
                reply_markup=_wallet_result_kb(),
            )
            return

        if reason == "already_paid":
            u = get_user(c.from_user.id, c.from_user.username)
            bot.answer_callback_query(c.id, "Уже зачислено")
            bot.send_message(c.message.chat.id, f"✅ Платеж уже был зачислен. Баланс: {u.balance}", reply_markup=_wallet_result_kb())
            return

        bot.answer_callback_query(c.id, "Ошибка")
        bot.send_message(c.message.chat.id, "Не удалось зачислить оплату автоматически. Обратитесь в поддержку.", reply_markup=_wallet_result_kb())

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.WAL + ":history"))
    def wallet_history(c: CallbackQuery):
        try:
            rows = list_balance_events(c.from_user.id, limit=30)
            if not rows:
                text = "📜 История операций по балансу\n\nПока операций нет."
            else:
                event_map = {
                    "topup": "Пополнение",
                    "order_payment": "Оплата заказа",
                    "order_income": "Выплата по заказу",
                    "order_refund": "Возврат за заказ",
                    "withdraw_approved": "Вывод средств",
                    "admin_adjustment": "Корректировка админом",
                    "manual_adjustment": "Ручная корректировка",
                }
                lines = ["📜 История операций по балансу (последние 30):"]
                for row in rows:
                    created = format_display_datetime(row.get("created_at"), fmt="%d.%m.%Y %H:%M", fallback="-")
                    delta = int(row.get("delta") or 0)
                    sign = "+" if delta > 0 else ""
                    ev = event_map.get(str(row.get("event_type") or ""), str(row.get("event_type") or "Операция"))
                    reason = str(row.get("reason") or "-")
                    lines.append(
                        f"• {sign}{delta} | {ev} | {reason} | {created}"
                    )
                text = "\n".join(lines)

            edit_message_any(bot, c.message, text, reply_markup=_history_kb())
        finally:
            bot.answer_callback_query(c.id)

    @bot.pre_checkout_query_handler(func=lambda q: True)
    def topup_pre_checkout(q: PreCheckoutQuery):
        try:
            payload = (q.invoice_payload or "").strip()
            payment = get_topup_payment_by_payload(payload)
            if not payment:
                bot.answer_pre_checkout_query(q.id, ok=False, error_message="Счет не найден. Создайте новый.")
                return

            if int(payment.get("user_id") or 0) != int(q.from_user.id):
                bot.answer_pre_checkout_query(q.id, ok=False, error_message="Этот счет создан для другого пользователя.")
                return

            if str(payment.get("payment_method") or "") != "stars":
                bot.answer_pre_checkout_query(q.id, ok=False, error_message="Неверный тип платежа.")
                return

            if str(payment.get("status") or "") != "pending":
                bot.answer_pre_checkout_query(q.id, ok=False, error_message="Этот счет уже обработан.")
                return

            if int(payment.get("stars_amount") or 0) != int(q.total_amount):
                bot.answer_pre_checkout_query(q.id, ok=False, error_message="Сумма счета изменилась. Создайте новый счет.")
                return

            bot.answer_pre_checkout_query(q.id, ok=True)
        except Exception:
            bot.answer_pre_checkout_query(q.id, ok=False, error_message="Ошибка проверки платежа. Повторите позже.")

    @bot.message_handler(content_types=["successful_payment"])
    def topup_success(m: Message):
        payment_data = m.successful_payment
        payload = (payment_data.invoice_payload or "").strip()
        rec = get_topup_payment_by_payload(payload)

        if not rec or str(rec.get("payment_method") or "") != "stars":
            return

        ok, reason = complete_topup_payment(
            payload=payload,
            telegram_payment_charge_id=getattr(payment_data, "telegram_payment_charge_id", None),
            provider_payment_charge_id=getattr(payment_data, "provider_payment_charge_id", None),
        )

        if ok:
            u = get_user(m.from_user.id, m.from_user.username)
            amount = int((rec or {}).get("amount") or 0)
            stars_amount = int((rec or {}).get("stars_amount") or getattr(payment_data, "total_amount", 0) or 0)
            bot.send_message(
                m.chat.id,
                (
                    "✅ Пополнение успешно.\n"
                    f"Зачислено: +{amount}\n"
                    f"Оплачено: {stars_amount} XTR\n"
                    f"Текущий баланс: {u.balance}"
                ),
                reply_markup=_wallet_result_kb(),
            )
            return

        if reason == "already_paid":
            bot.send_message(m.chat.id, "ℹ️ Этот платеж уже был обработан ранее.", reply_markup=_wallet_result_kb())
            return

        bot.send_message(
            m.chat.id,
            "Не удалось зачислить оплату автоматически. Обратитесь в поддержку и укажите время платежа.",
            reply_markup=_wallet_result_kb(),
        )
