# backend/app/services/acl_matrix.py

TEAM_PERMISSIONS = {
    "owner": {
        "can_invite": True,
        "can_remove": True,
        "can_change_role": True,
        "can_view_usage": True,
        "can_view_billing": True,
        "can_manage_billing": True,
        "can_use_tools": True,
    },
    "admin": {
        "can_invite": True,
        "can_remove": True,
        "can_change_role": False,
        "can_view_usage": True,
        "can_view_billing": False,
        "can_manage_billing": False,
        "can_use_tools": True,
    },
    "member": {
        "can_invite": False,
        "can_remove": False,
        "can_change_role": False,
        "can_view_usage": False,
        "can_view_billing": False,
        "can_manage_billing": False,
        "can_use_tools": True,
    },
    "viewer": {
        "can_invite": False,
        "can_remove": False,
        "can_change_role": False,
        "can_view_usage": False,
        "can_view_billing": False,
        "can_manage_billing": False,
        "can_use_tools": False,
    },
}


def check_permission(role: str, permission: str) -> bool:
    if role not in TEAM_PERMISSIONS:
        return False
    return TEAM_PERMISSIONS[role].get(permission, False)
