from backend.app.services.api_key_service import get_user_from_api_key

user, key_row = get_user_from_api_key(api_key)

if not user:
    return JSONResponse(
        status_code=401,
        content={"detail": "Invalid or inactive API key"}
    )

# attach to request.state
request.state.api_user = user
request.state.api_key_row = key_row
from backend.app.services.usage_service import log_usage

response = await call_next(request)

# log usage after request is processed
user = getattr(request.state, "api_user", None)
key_row = getattr(request.state, "api_key_row", None)

if user:
    try:
        log_usage(user, key_row, request, response.status_code)
    except Exception:
        pass

return response
