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
