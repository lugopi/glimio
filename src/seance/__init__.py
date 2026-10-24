__version__ = '0.5.0'

# Frozen releases may install optional provider wheels into a user-managed
# CPython site-packages directory. Add that path before provider modules load.
from .provider_runtime import activate_managed_provider_runtime as _activate_managed_provider_runtime

_activate_managed_provider_runtime()
del _activate_managed_provider_runtime
