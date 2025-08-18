# accounts/utils.py

from datetime import datetime, timedelta

def get_current_week_dates():
    """Возвращает список объектов date для текущей недели (с понедельника по воскресенье)."""
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday()) # Понедельник
    return [start_of_week + timedelta(days=i) for i in range(7)]

def get_week_range(date):
    start_of_week = date - timedelta(days=date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week