# finance/accounting.py   (new file – can be imported anywhere)
from django.core.exceptions import ObjectDoesNotExist
from .models import Account

def get_account(code: str) -> Account:
    """
    Returns the Account with the given code.
    Raises ObjectDoesNotExist if not found – caller must handle it.
    """
    return Account.objects.get(code=code)