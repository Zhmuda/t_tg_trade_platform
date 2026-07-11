import os
from decimal import Decimal

from t_tech.invest import MoneyValue
from t_tech.invest.sandbox.client import SandboxClient
from t_tech.invest.utils import decimal_to_quotation, quotation_to_decimal

TOKEN = os.environ["TINKOFF_SANDBOX_TOKEN"]


def main():
    with SandboxClient(TOKEN) as client:
        accounts = client.users.get_accounts().accounts
        print(f"Найдено sandbox-счетов: {len(accounts)}")

        if accounts:
            account_id = accounts[0].id
            print(f"Использую существующий счёт: {account_id}")
        else:
            account_id = client.sandbox.open_sandbox_account().account_id
            print(f"Создан новый sandbox-счёт: {account_id}")
            quotation = decimal_to_quotation(Decimal(100_000))
            client.sandbox.sandbox_pay_in(
                account_id=account_id,
                amount=MoneyValue(units=quotation.units, nano=quotation.nano, currency="rub"),
            )
            print("Пополнил счёт на 100 000 виртуальных рублей")

        positions = client.operations.get_positions(account_id=account_id)

        rub_balance = 0.0
        for money in positions.money:
            if money.currency == "rub":
                rub_balance = float(quotation_to_decimal(money))

        print(f"Баланс счёта: {rub_balance:,.2f} руб.")
        print(f"Открытых позиций по бумагам: {len(positions.securities)}")


if __name__ == "__main__":
    main()
