from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Literal

import kfactory as kf
from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

from gdsfactory.component import Component, boolean_operations

if TYPE_CHECKING:
    from gdsfactory.technology import LayerViews


class LayerLevel(BaseModel):
    """Level for 3D LayerStack.

    Parameters:
        layer: (GDSII Layer number, GDSII datatype).
        thickness: layer thickness in um.
        thickness_tolerance: layer thickness tolerance in um.
        zmin: height position where material starts in um.
        zmin_tolerance: layer height tolerance in um.
        material: material name.
        sidewall_angle: in degrees with respect to normal.
        sidewall_angle_tolerance: in degrees.
        width_to_z: if sidewall_angle, relative z-position (0 --> zmin, 1 --> zmin + thickness).
        z_to_bias: parametrizes shrinking/expansion of the design GDS layer \
                when extruding from zmin (0) to zmin + thickness (1).\
                Defaults no buffering [[0, 1], [0, 0]].
        mesh_order: lower mesh order (1) will have priority over higher \
                mesh order (2) in the regions where materials overlap.
        refractive_index: int, complex or function that depends on wavelength (um).
        type: grow, etch, implant, or background.
        mode: octagon, taper, round. https://gdsfactory.github.io/klayout_pyxs/DocGrow.html
        into: etch into another layer. https://gdsfactory.github.io/klayout_pyxs/DocGrow.html
        resistivity: for metals.
        bias: in um for the etch. Can be a single number or 2 numbers (bias_x, bias_y)
        derived_layer: Optional derived layer, used for layer_type='etch' to define the slab.
        info: simulation_info and other types of metadata.
        background_doping_concentration: uniform base doping level in the material (cm-3)
        background_doping_ion: uniform base doping ion in the material
        orientation: of the wafer (Miller indices of the plane)
    """

    name: str | None = None
    layer: kf.LayerEnum | tuple[int, int] | None = None
    thickness: float
    thickness_tolerance: float | None = None
    zmin: float
    zmin_tolerance: float | None = None
    material: str | None = None
    sidewall_angle: float = 0.0
    sidewall_angle_tolerance: float | None = None
    width_to_z: float = 0.0
    z_to_bias: tuple[list[float], list[float]] | None = None
    mesh_order: int = 3
    layer_type: Literal["grow", "etch", "implant", "background"] = "grow"
    mode: Literal["octagon", "taper", "round"] | None = None
    into: list[str] | None = None
    resistivity: float | None = None
    bias: tuple[float, float] | float | None = None
    derived_layer: tuple[int, int] | None = None
    info: dict[str, Any] = Field(default_factory=dict)
    background_doping_concentration: float | None = None
    background_doping_ion: str | None = None
    orientation: str | None = "100"

    @property
    def bounds(self) -> tuple[float, float]:
        """Calculates and returns the bounds of the layer level in the z-direction.

        Returns:
            tuple: A tuple containing the minimum and maximum z-values of the layer level.
        """
        return tuple(sorted([self.zmin, self.zmin + self.thickness]))


class LayerStack(BaseModel):
    """For simulation and 3D rendering. Captures design intent of the chip layers after fabrication.

    Parameters:
        layers: dict of layer_levels.
    """

    layers: dict[str, LayerLevel] = Field(
        default_factory=dict,
        description="dict of layer_levels",
    )

    def model_copy(self) -> LayerStack:
        """Returns a copy of the LayerStack."""
        return LayerStack.model_validate_json(self.model_dump_json())

    def __init__(self, **data: Any) -> None:
        """Add LayerLevels automatically for subclassed LayerStacks."""
        super().__init__(**data)

        for field in self.model_dump():
            val = getattr(self, field)
            if isinstance(val, LayerLevel):
                self.layers[field] = val

    def pprint(self) -> None:
        console = Console()
        table = Table(show_header=True, header_style="bold")
        keys = ["layer", "thickness", "material", "sidewall_angle"]

        for key in ["name"] + keys:
            table.add_column(key)

        for layer_name, layer in self.layers.items():
            port_dict = dict(layer)
            row = [layer_name] + [str(port_dict.get(key, "")) for key in keys]
            table.add_row(*row)

        console.print(table)

    def get_layer_to_thickness(self) -> dict[tuple[int, int], float]:
        """Returns layer tuple to thickness (um)."""
        layer_to_thickness = {}

        for level in self.layers.values():
            layer = level.layer

            if layer and level.thickness:
                layer_to_thickness[layer] = level.thickness
            elif hasattr(level, "operator"):
                layer_to_thickness[level.layer] = level.thickness

        return layer_to_thickness

    def get_component_with_derived_layers(self, component, **kwargs):
        """Returns component with derived layers."""
        return get_component_with_derived_layers(
            component=component, layer_stack=self, **kwargs
        )

    def get_layer_to_zmin(self) -> dict[tuple[int, int], float]:
        """Returns layer tuple to z min position (um)."""
        return {
            level.layer: level.zmin for level in self.layers.values() if level.thickness
        }

    def get_layer_to_material(self) -> dict[tuple[int, int], str]:
        """Returns layer tuple to material name."""
        return {
            level.layer: level.material
            for level in self.layers.values()
            if level.thickness
        }

    def get_layer_to_sidewall_angle(self) -> dict[tuple[int, int], str]:
        """Returns layer tuple to material name."""
        return {
            level.layer: level.sidewall_angle
            for level in self.layers.values()
            if level.thickness
        }

    def get_layer_to_info(self) -> dict[tuple[int, int], dict]:
        """Returns layer tuple to info dict."""
        return {level.layer: level.info for level in self.layers.values()}

    def get_layer_to_layername(self) -> dict[tuple[int, int], str]:
        """Returns layer tuple to layername."""
        d = defaultdict(list)
        for level_name, level in self.layers.items():
            d[level.layer].append(level_name)

        return d

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {level_name: dict(level) for level_name, level in self.layers.items()}

    def __getitem__(self, key) -> LayerLevel:
        """Access layer stack elements."""
        if key not in self.layers:
            layers = list(self.layers.keys())
            raise ValueError(f"{key!r} not in {layers}")

        return self.layers[key]

    def get_klayout_3d_script(
        self,
        layer_views: LayerViews | None = None,
        dbu: float | None = 0.001,
    ) -> str:
        """Returns script for 2.5D view in KLayout.

        You can include this information in your tech.lyt

        Args:
            layer_views: optional layer_views.
            dbu: Optional database unit. Defaults to 1nm.
        """
        layers = self.layers or {}

        unetched_layers = [
            layer_name
            for layer_name, level in layers.items()
            if level.layer and level.layer_type == "grow"
        ]
        etch_layers = [
            layer_name
            for layer_name, level in layers.items()
            if level.layer and level.layer_type == "etch"
        ]

        # remove all etched layers from the grown layers
        unetched_layers_dict = defaultdict(list)
        for layer_name in etch_layers:
            level = layers[layer_name]
            into = level.into or []
            for layer_name_etched in into:
                unetched_layers_dict[layer_name_etched].append(layer_name)
                if layer_name_etched in unetched_layers:
                    unetched_layers.remove(layer_name_etched)

        # define layers
        out = "\n".join(
            [
                f"{layer_name} = input({level.layer[0]}, {level.layer[1]})"
                for layer_name, level in layers.items()
                if level.layer
            ]
        )
        out += "\n"
        out += "\n"

        # define unetched layers
        for layer_name_etched, etching_layers in unetched_layers_dict.items():
            etching_layers = " - ".join(etching_layers)
            out += f"unetched_{layer_name_etched} = {layer_name_etched} - {etching_layers}\n"

        out += "\n"

        # define slabs
        for layer_name, level in layers.items():
            if level.layer_type == "etch":
                into = level.into or []
                for i, layer1 in enumerate(into):
                    out += f"slab_{layer1}_{layer_name}_{i} = {layer1} &amp; {layer_name}\n"

        out += "\n"

        for layer_name, level in layers.items():
            layer = level.layer
            zmin = level.zmin
            zmax = zmin + level.thickness
            if dbu:
                rnd_pl = len(str(dbu).split(".")[-1])
                zmin = round(zmin, rnd_pl)
                zmax = round(zmax, rnd_pl)

            if layer is None:
                continue

            elif level.layer_type == "etch":
                name = f"{layer_name}: {level.material}"

                into = level.into or []
                for i, layer1 in enumerate(into):
                    unetched_level = layers[layer1]
                    unetched_zmin = unetched_level.zmin
                    unetched_zmax = unetched_zmin + unetched_level.thickness

                    # slab
                    slab_layer_name = f"slab_{layer1}_{layer_name}_{i}"
                    slab_zmin = unetched_level.zmin
                    slab_zmax = unetched_zmax - level.thickness
                    name = f"{slab_layer_name}: {level.material} {layer[0]}/{layer[1]}"
                    txt = (
                        f"z("
                        f"{slab_layer_name}, "
                        f"zstart: {slab_zmin}, "
                        f"zstop: {slab_zmax}, "
                        f"name: '{name}'"
                    )
                    if layer_views:
                        txt += ", "
                        props = layer_views.get_from_tuple(layer)
                        if hasattr(props, "color"):
                            if props.color.fill == props.color.frame:
                                txt += f"color: {props.color.fill}"
                            else:
                                txt += (
                                    f"fill: {props.color.fill}, "
                                    f"frame: {props.color.frame}"
                                )
                    txt += ")"
                    out += f"{txt}\n"

            elif layer_name in unetched_layers:
                name = f"{layer_name}: {level.material} {layer[0]}/{layer[1]}"

                txt = (
                    f"z("
                    f"{layer_name}, "
                    f"zstart: {zmin}, "
                    f"zstop: {zmax}, "
                    f"name: '{name}'"
                )
                if layer_views:
                    txt += ", "
                    props = layer_views.get_from_tuple(layer)
                    if hasattr(props, "color"):
                        if props.color.fill == props.color.frame:
                            txt += f"color: {props.color.fill}"
                        else:
                            txt += (
                                f"fill: {props.color.fill}, "
                                f"frame: {props.color.frame}"
                            )

                txt += ")"
                out += f"{txt}\n"

        out += "\n"

        for layer_name in unetched_layers_dict:
            unetched_level = self.layers[layer_name]
            layer = unetched_level.layer

            unetched_zmin = unetched_level.zmin
            unetched_zmax = unetched_zmin + unetched_level.thickness
            name = f"{slab_layer_name}: {unetched_level.material}"

            unetched_layer_name = f"unetched_{layer_name}"
            name = f"{unetched_layer_name}: {unetched_level.material} {layer[0]}/{layer[1]}"
            txt = (
                f"z("
                f"{unetched_layer_name}, "
                f"zstart: {unetched_zmin}, "
                f"zstop: {unetched_zmax}, "
                f"name: '{name}'"
            )
            if layer_views:
                txt += ", "
                props = layer_views.get_from_tuple(layer)
                if hasattr(props, "color"):
                    if props.color.fill == props.color.frame:
                        txt += f"color: {props.color.fill}"
                    else:
                        txt += (
                            f"fill: {props.color.fill}, " f"frame: {props.color.frame}"
                        )
            txt += ")"
            out += f"{txt}\n"

        return out

    def filtered(self, layers) -> LayerStack:
        """Returns filtered layerstack, given layer specs."""
        return LayerStack(
            layers={k: self.layers[k] for k in layers if k in self.layers}
        )

    def z_offset(self, dz) -> LayerStack:
        """Translates the z-coordinates of the layerstack."""
        layers = self.layers or {}
        for layer in layers.values():
            layer.zmin += dz

        return self

    def invert_zaxis(self) -> LayerStack:
        """Flips the zmin values about the origin."""
        layers = self.layers or {}
        for layer in layers.values():
            layer.zmin *= -1

        return self


def get_component_with_derived_layers(component, layer_stack: LayerStack) -> Component:
    """Returns a component with derived layers.

    Args:
        component: Component to get derived layers for.
        layer_stack: Layer stack to get derived layers from.
    """
    from gdsfactory.pdk import get_layer

    unetched_layers = [
        layer_name
        for layer_name, level in layer_stack.layers.items()
        if level.layer and level.layer_type == "grow"
    ]
    etch_layers = [
        layer_name
        for layer_name, level in layer_stack.layers.items()
        if level.layer and level.layer_type == "etch"
    ]

    # remove all etched layers from the grown layers
    unetched_layers_dict = defaultdict(list)
    for layer_name in etch_layers:
        level = layer_stack.layers[layer_name]
        into = level.into or []
        for layer_name_etched in into:
            unetched_layers_dict[layer_name_etched].append(layer_name)
            if layer_name_etched in unetched_layers:
                unetched_layers.remove(layer_name_etched)

    polygons_per_layer = component.get_polygons()
    component_layers = polygons_per_layer.keys()

    # Define pure grown layers
    unetched_layer_numbers = [
        layer_stack.layers[layer_name].layer
        for layer_name in unetched_layers
        if layer_stack.layers[layer_name].layer in component_layers
    ]
    component_derived = component.extract(unetched_layer_numbers)

    # Define unetched layers
    for unetched_layer_name, unetched_layers in unetched_layers_dict.items():
        layer_index = layer_stack.layers[unetched_layer_name].layer
        polygons = polygons_per_layer[layer_index]
        for polygon in polygons:
            component_derived.shapes(layer_index).insert(polygon)

        # Add all the etching layers (OR)
        polygons_to_remove = kf.kdb.Region()

        for etching_layers in unetched_layers:
            layer = layer_stack.layers[etching_layers].layer
            if layer in polygons_per_layer:
                layer_index = get_layer(layer)
                B_polys = polygons_per_layer[layer]
                r2 = kf.kdb.Region(B_polys)
                polygons_to_remove = polygons_to_remove | r2

                derived_layer = layer_stack.layers[etching_layers].derived_layer
                if derived_layer:
                    r1 = polygons
                    r2 = B_polys
                    operation = "and"

                    r1 = kf.kdb.Region(r1)
                    r2 = kf.kdb.Region(r2)
                    f = boolean_operations[operation]
                    r = f(r1, r2)
                    r = component_derived.shapes(layer_index).insert(r)

        # Remove all etching layers
        layer = layer_stack.layers[unetched_layer_name].layer
        polygons = polygons_per_layer[layer]
        f = boolean_operations["not"]
        r = f(polygons, polygons_to_remove)
        r = component_derived.shapes(layer_index).insert(r)

    component_derived.add_ports(component.ports)
    return component_derived


if __name__ == "__main__":
    import gdsfactory as gf
    from gdsfactory.generic_tech import LAYER_STACK

    layer_stack = LAYER_STACK

    c = gf.components.grating_coupler_elliptical_trenches()
    c = c.to_3d()
    c.show()

    # import gdsfactory as gf
    # from gdsfactory.generic_tech import LAYER_STACK
    # component = c = gf.components.grating_coupler_elliptical_trenches()
    # component = c = gf.components.taper_strip_to_ridge_trenches()
    # script = LAYER_STACK.get_klayout_3d_script()
    # print(script)
    # ls = layer_stack = LAYER_STACK
    # layer_to_thickness = layer_stack.get_layer_to_thickness()
    # c = layer_stack.get_component_with_derived_layers(component)
    # c.show()
    # import pathlib
    # filepath = pathlib.Path(
    #     "/home/jmatres/gdslib/sp/temp/write_sparameters_meep_mpi.json"
    # )
    # ls_json = filepath.read_bytes()
    # ls2 = LayerStack.parse_raw(ls_json)
    # from gdsfactory.generic_tech import LAYER_STACK
    # from gdsfactory.technology.klayout_tech import KLayoutTechnology

    # lyp = LayerViews.from_lyp(str(PATH.klayout_lyp))

    # # str_xml = open(PATH.klayout_tech / "tech.lyt").read()
    # # new_tech = db.Technology.technology_from_xml(str_xml)
    # # generic_tech = KLayoutTechnology(layer_views=lyp)
    # connectivity = [("M1", "VIA1", "M2"), ("M2", "VIA2", "M3")]

    # c = generic_tech = KLayoutTechnology(
    #     name="generic_tech", layer_views=lyp, connectivity=connectivity
    # )
    # tech_dir = PATH.klayout_tech
    # # tech_dir = pathlib.Path("/home/jmatres/.klayout/salt/gdsfactory/tech/")
    # tech_dir.mkdir(exist_ok=True, parents=True)
    # generic_tech.write_tech(tech_dir=tech_dir, layer_stack=LAYER_STACK)

    # yaml_test()
