import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _install_openenv_test_stubs() -> None:
    """Provide minimal openenv modules so unit tests run offline."""
    if "openenv.core.env_server.types" in sys.modules and "openenv.core.env_server.interfaces" in sys.modules:
        return

    openenv_module = types.ModuleType("openenv")
    core_module = types.ModuleType("openenv.core")
    env_server_module = types.ModuleType("openenv.core.env_server")
    types_module = types.ModuleType("openenv.core.env_server.types")
    interfaces_module = types.ModuleType("openenv.core.env_server.interfaces")

    class _BaseModelLike:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    class Action(_BaseModelLike):
        pass

    class Observation(_BaseModelLike):
        pass

    class State(_BaseModelLike):
        def __init__(self, episode_id: str = "", step_count: int = 0, **kwargs):
            super().__init__(episode_id=episode_id, step_count=step_count, **kwargs)

    class EnvironmentMetadata(_BaseModelLike):
        pass

    class Environment:
        pass

    types_module.Action = Action
    types_module.Observation = Observation
    types_module.State = State
    types_module.EnvironmentMetadata = EnvironmentMetadata
    interfaces_module.Environment = Environment

    openenv_module.core = core_module
    core_module.env_server = env_server_module
    env_server_module.types = types_module
    env_server_module.interfaces = interfaces_module

    sys.modules["openenv"] = openenv_module
    sys.modules["openenv.core"] = core_module
    sys.modules["openenv.core.env_server"] = env_server_module
    sys.modules["openenv.core.env_server.types"] = types_module
    sys.modules["openenv.core.env_server.interfaces"] = interfaces_module


_install_openenv_test_stubs()
