from worlds.LauncherComponents import Component, Type, components, launch as launch_component

from .world import WellDwellerWorld


def launch_client(*args: str) -> None:
    from .client import launch
    launch_component(launch, name="Well Dweller Client", args=args)


components.append(Component("Well Dweller Client", func=launch_client, component_type=Type.CLIENT))

__all__ = ["WellDwellerWorld"]
