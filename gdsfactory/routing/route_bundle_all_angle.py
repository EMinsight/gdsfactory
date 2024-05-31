from collections.abc import Sequence
from functools import partial

import kfactory as kf
from kfactory.routing.aa.optical import (
    BendFactory,
    OpticalAllAngleRoute,
    StraightFactory,
    route_bundle,
)

from gdsfactory.components.bend_euler import bend_euler_all_angle
from gdsfactory.components.straight import straight_all_angle
from gdsfactory.typings import ComponentSpec, Port


def route_bundle_all_angle(
    component: ComponentSpec,
    ports1: list[Port],
    ports2: list[Port],
    backbone: Sequence[tuple[float, float]] | None = None,
    separation: list[float] | float = 3.0,
    straight_factory: StraightFactory = straight_all_angle,
    bend_factory: BendFactory = partial(bend_euler_all_angle, radius=5),
    bend_ports: tuple[str, str] = ("o1", "o2"),
    straight_ports: tuple[str, str] = ("o1", "o2"),
) -> list[OpticalAllAngleRoute]:
    """Route a bundle of ports to another bundle of ports with all angles.

    Args:
        component: to add the routing.
        ports1: list of start ports to connect.
        ports2: list of end ports to connect.
        backbone: list of points to connect the ports.
        separation: list of spacings.
        straight_factory: factory to create straights.
        bend_factory: factory to create bends.
        bend_ports: tuple of ports to connect the bends.
        straight_ports: tuple of ports to connect the straights.
    """
    backbone = backbone or []
    if backbone:
        backbone = [kf.kdb.DPoint(*p) for p in backbone]

    return route_bundle(
        c=component,
        start_ports=ports1,
        end_ports=ports2,
        backbone=backbone,
        separation=separation,
        straight_factory=straight_factory,
        bend_factory=bend_factory,
        bend_ports=bend_ports,
        straight_ports=straight_ports,
    )


if __name__ == "__main__":
    import gdsfactory as gf

    # c = gf.Component()
    # rows = 3
    # w1 = c << gf.c.array("straight", spacing=(0, 10), rows=rows, columns=1)
    # w2 = c << gf.c.array("straight", spacing=(0, 10), rows=rows, columns=1)
    # w2.drotate(-30)
    # w2.dmovex(140)
    # p1 = list(w1.ports.filter(orientation=0))
    # p2 = list(w2.ports.filter(orientation=150))
    # p1.reverse()
    # p2.reverse()

    # c1 = np.array(p2[0].dcenter)
    # c2 = np.array(p1[0].dcenter)
    # d = (np.array(p2[0].dcenter) + np.array(p1[0].dcenter)) / 2
    # backbone = [
    #     d - (10.0, 0),
    #     d + (10.0, 0),
    # ]

    # route_bundle_all_angle(
    #     c,
    #     p1,
    #     p2,
    #     backbone=backbone,
    #     separation=3,
    # )

    c = gf.Component()

    mmi = gf.components.mmi2x2(width_mmi=10, gap_mmi=3)
    mmi1 = c.create_vinst(mmi)  # create a virtual instance
    mmi2 = c.create_vinst(mmi)  # create a virtual instance

    mmi2.move((100, 10))
    mmi2.rotate(30)

    routes = gf.routing.route_bundle_all_angle(
        c,
        mmi1.ports.filter(orientation=0),
        [mmi2.ports["o2"], mmi2.ports["o1"]],
    )

    c.show()
