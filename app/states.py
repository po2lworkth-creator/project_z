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


class SellerStates(StatesGroup):
    waiting_phone_contact = State()


class AdminPanelStates(StatesGroup):
    profile_wait_tg_id = State()
    balance_wait_tg_id = State()
    balance_wait_new_value = State()
    ban_wait_tg_id = State()


class SuperAdminPanelStates(StatesGroup):
    profile_wait_tg_id = State()
    balance_wait_tg_id = State()
    balance_wait_new_value = State()
    ban_wait_tg_id = State()
    admin_grant_wait_tg_id = State()
    admin_revoke_wait_tg_id = State()
