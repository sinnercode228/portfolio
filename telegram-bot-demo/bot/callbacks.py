"""Фабрики callback_data для inline-кнопок (типизированные, с валидацией aiogram)."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCb(CallbackData, prefix="menu"):
    section: str  # services | prices | apply | faq | contacts | home


class FormCb(CallbackData, prefix="form"):
    action: str  # use_tg_name | skip_comment | submit | edit | back | cancel


class ServiceCb(CallbackData, prefix="svc"):
    code: str


class EditCb(CallbackData, prefix="edit"):
    field: str  # name | phone | service | comment


class LeadStatusCb(CallbackData, prefix="lead"):
    lead_id: int
    status: str


class BroadcastCb(CallbackData, prefix="bc"):
    action: str  # send | cancel
