from aiogram.fsm.state import State, StatesGroup


class TokenStates(StatesGroup):
    waiting_for_token = State()


class BacktestFlow(StatesGroup):
    choosing_strategy = State()
    entering_ticker = State()
    choosing_period = State()


class StrategyFlow(StatesGroup):
    choosing_strategy = State()
    choosing_sentiment = State()
    entering_ticker = State()
    confirming_real = State()


class NewsFlow(StatesGroup):
    entering_ticker = State()
    choosing_period = State()
