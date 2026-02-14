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
