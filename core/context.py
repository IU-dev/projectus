from .permissions import SystemPermission, has_system_permission
def navigation(request):
    return {"show_operations": any(has_system_permission(request.user, p) for p in SystemPermission)}
