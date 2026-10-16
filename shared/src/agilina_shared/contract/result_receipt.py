from typing import Literal

from agilina_shared.contract.contract_model import ContractModel


class ResultReceipt(ContractModel):
    """The API's answer when it accepts a result, also when the same result arrives again."""

    status: Literal["received"] = "received"
