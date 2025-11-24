# backend/app/services/acl_matrix.py
"""
Team Role Permissions Matrix

This file defines all team permission rules. 
Used by team ACL middleware and team-based route guards.
"""

from typing import Dict, Any


# -----------------------------------------
# TEAM PERMISSION MATRIX
# -----------------------------------------
TEAM_PERMISSIONS: Dict[str, Dict[str, bool]] = {
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

ALLOWED_PERMISSIONS = {
    "can_invite",
    "can_remove",
    "can_change_role",
    "can_view_usage",
    "can_view_billing",
    "can_manage_billing",
    "can_use_tools",
}


# -----------------------------------------
# Permission Checker
# -----------------------------------------
def check_permission(role: str, permission: str) -> bool:
    """
    Returns True if the role has the requested permission.
    Handles:
    - invalid roles
    - invalid permissions
    - missing permission keys
    """
    role = role.lower()

    if role not in TEAM_PERMISSIONS:
        return False

    if permission not in ALLOWED_PERMISSIONS:
        return False

    return TEAM_PERMISSIONS[role].get(permission, False)
