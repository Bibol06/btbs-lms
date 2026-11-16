"""Administrative responsibilities are independent of course assignments."""
def is_admin(user):
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or user.role == 'admin'))


def scope(user):
    return 'full' if user.is_superuser else getattr(user, 'admin_scope', 'full')


def is_system_admin(user):
    return is_admin(user) and scope(user) in ['full', 'system']


def is_learning_admin(user):
    return is_admin(user) and scope(user) in ['full', 'learning']


def is_full_admin(user):
    return is_admin(user) and scope(user) == 'full'


def access_data(user):
    return {'admin_scope': scope(user) if is_admin(user) else None,
        'capabilities': {'system_admin': is_system_admin(user), 'learning_admin': is_learning_admin(user),
                         'manage_accounts': is_system_admin(user), 'manage_admin_roles': is_full_admin(user)}}
