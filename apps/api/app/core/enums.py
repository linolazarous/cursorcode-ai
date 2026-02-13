from enum import Enum

class Plan(str, Enum):
    starter = "starter"
    standard = "standard"
    pro = "pro"
    premier = "premier"
    ultra = "ultra"
