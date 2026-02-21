from telebot.handler_backends import StatesGroup, State

class ChatStates(StatesGroup):
    waiting_seller_id = State()
    chatting = State()

class WalletStates(StatesGroup):
    topup_amount = State()
    withdraw_amount = State()
    withdraw_details = State()

class SupportStates(StatesGroup):
    waiting_message = State()
    waiting_reply = State()
    waiting_withdraw_reason = State()
    waiting_withdraw_amount = State()
    waiting_withdraw_phone = State()
    waiting_withdraw_bank = State()

class SellerStates(StatesGroup):
    waiting_phone_contact = State()


class ListingStates(StatesGroup):
    waiting_title = State()
    waiting_short_desc = State()
    waiting_full_desc = State()
    waiting_price = State()


class AdminPanelStates(StatesGroup):
    profile_wait_tg_id = State()
    balance_wait_tg_id = State()
    balance_wait_new_value = State()
    ban_wait_tg_id = State()
    seller_revoke_wait_tg_id = State()
    message_wait_tg_id = State()
    message_wait_text = State()
    broadcast_wait_text = State()


class SuperAdminPanelStates(StatesGroup):
    profile_wait_tg_id = State()
    balance_wait_tg_id = State()
    balance_wait_new_value = State()
    ban_wait_tg_id = State()
    seller_revoke_wait_tg_id = State()
    message_wait_tg_id = State()
    message_wait_text = State()
    broadcast_wait_text = State()

    admin_grant_wait_tg_id = State()
    admin_revoke_wait_tg_id = State()
