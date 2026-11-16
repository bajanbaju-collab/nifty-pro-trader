"""Read-only Kite connectivity adapter. There is deliberately no order method."""

from urllib.parse import quote


class KiteBroker:
    def __init__(self, api_key: str, access_token: str):
        if not api_key or not access_token:
            raise ValueError("Missing Kite credentials")
        from kiteconnect import KiteConnect
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)

    def profile(self) -> dict:
        return self.kite.profile()

    def quote(self, instruments: list[str]) -> dict:
        return self.kite.quote(instruments)


def login_url(api_key: str, nonce: str) -> str:
    from kiteconnect import KiteConnect
    return KiteConnect(api_key=api_key).login_url() + "&redirect_params=" + quote("nonce=" + nonce, safe="")


def exchange_request_token(api_key: str, api_secret: str, request_token: str) -> dict:
    from kiteconnect import KiteConnect
    return KiteConnect(api_key=api_key).generate_session(request_token, api_secret=api_secret)
