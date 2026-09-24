"""Состояния конечного автомата (FSM)."""

from aiogram.fsm.state import State, StatesGroup


class LeadForm(StatesGroup):
    name = State()
    phone = State()
    service = State()
    comment = State()
    confirm = State()


class BroadcastForm(StatesGroup):
    waiting_message = State()
    confirm = State()
