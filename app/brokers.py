"""Read-only Kite connectivity adapter. There is deliberately no order method."""


class KiteBroker:
    def __init__(self, api_key: str, access_token: str):
        if not api_key or not access_token:
            raise ValueError("Missing Kite credentials")
        from kiteconnect import KiteConnect

        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)

    def profile(self) -> dict:
        return self.kite.profile()
