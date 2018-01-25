from collections import OrderedDict
import bpy
from bpy.props import StringProperty, IntProperty
from .. import utils
from .node_tree import poll_object, make_nodetree_name


def new_node(bl_idname, node_tree, previous_node, output=0, input=0):
    node = node_tree.nodes.new(bl_idname)
    node.location = (previous_node.location.x - 250, previous_node.location.y)
    node_tree.links.new(node.outputs[output], previous_node.inputs[input])
    return node


class LUXCORE_OT_preset_material(bpy.types.Operator):
    bl_idname = "luxcore.preset_material"
    bl_label = ""
    bl_description = "Add a pre-definied node setup"

    basic_mapping = OrderedDict([
        ("Mix", "LuxCoreNodeMatMix"),
        ("Glossy", "LuxCoreNodeMatGlossy2"),
        ("Glass", "LuxCoreNodeMatGlass"),
        ("Null (Transparent)", "LuxCoreNodeMatNull"),
        ("Metal", "LuxCoreNodeMatMetal"),
        ("Mirror", "LuxCoreNodeMatMirror"),
        ("Glossy Translucent", "LuxCoreNodeMatGlossyTranslucent"),
        ("Matte Translucent", "LuxCoreNodeMatMatteTranslucent"),
    ])

    preset = StringProperty()
    categories = OrderedDict([
        ("Basic", list(basic_mapping.keys())),
        ("Advanced", [
            "Smoke",
            "Fire and Smoke",
        ]),
    ])

    @classmethod
    def poll(cls, context):
        return poll_object(context)

    def _add_node_tree(self, name):
        node_tree = bpy.data.node_groups.new(name=name, type="luxcore_material_nodes")
        node_tree.use_fake_user = True
        return node_tree

    def execute(self, context):
        mat = context.material
        obj = context.object

        if mat is None:
            # We need to create a material
            mat = bpy.data.materials.new(name="Material")

            # Attach the new material to the active object
            if obj.material_slots:
                obj.material_slots[obj.active_material_index].material = mat
            else:
                obj.data.materials.append(mat)

        # We have a material, but maybe it has no node tree attached
        node_tree = mat.luxcore.node_tree

        if node_tree is None:
            tree_name = make_nodetree_name(mat.name)
            node_tree = self._add_node_tree(tree_name)
            mat.luxcore.node_tree = node_tree

        nodes = node_tree.nodes

        # Add the new nodes below all other nodes
        # x location should be centered (average of other nodes x positions)
        # y location shoud be below all others
        location_x = 300
        location_y = 500

        for node in nodes:
            location_x = max(node.location.x, location_x)
            location_y = min(node.location.y, location_y)
            # De-select all nodes
            node.select = False

        # Create an output for the new nodes
        output = nodes.new("LuxCoreNodeMatOutput")
        output.location = (location_x, location_y - 300)
        output.select = False

        # Category: Basic
        if self.preset in self.basic_mapping:
            new_node(self.basic_mapping[self.preset], node_tree, output)
        # Category: Advanced
        elif self.preset == "Smoke":
            self._preset_smoke(obj, node_tree, output)
        elif self.preset == "Fire and Smoke":
            self._preset_fire_and_smoke(obj, node_tree, output)

        return {"FINISHED"}

    def _preset_smoke(self, obj, node_tree, output):
        # If it is not a smoke domain, create the material anyway, but warn the user
        is_smoke_domain = utils.find_smoke_domain_modifier(obj)

        new_node("LuxCoreNodeMatNull", node_tree, output)

        # We need a volume
        name = "Smoke Volume"
        vol_node_tree = bpy.data.node_groups.new(name=name, type="luxcore_volume_nodes")
        vol_nodes = vol_node_tree.nodes
        # Attach to output node
        output.interior_volume = vol_node_tree

        # Add volume nodes
        vol_output = vol_nodes.new("LuxCoreNodeVolOutput")
        vol_output.location = 300, 200

        heterogeneous = new_node("LuxCoreNodeVolHeterogeneous", vol_node_tree, vol_output)
        smoke_node = new_node("LuxCoreNodeTexSmoke", vol_node_tree, heterogeneous, 0, "Scattering")
        if is_smoke_domain:
            smoke_node.domain = obj
        smoke_node.source = "density"
        smoke_node.wrap = "black"

        # A smoke material setup only makes sense on the smoke domain object
        if not is_smoke_domain:
            self.report({"ERROR"}, 'Object "%s" is not a smoke domain!' % obj.name)

    def _preset_fire_and_smoke(self, obj, node_tree, output):
        # If it is not a smoke domain, create the material anyway, but warn the user
        is_smoke_domain = utils.find_smoke_domain_modifier(obj)

        new_node("LuxCoreNodeMatNull", node_tree, output)

        # We need a volume
        name = "Fire and Smoke Volume"
        vol_node_tree = bpy.data.node_groups.new(name=name, type="luxcore_volume_nodes")
        vol_nodes = vol_node_tree.nodes
        # Attach to output node
        output.interior_volume = vol_node_tree

        # Add volume nodes
        vol_output = vol_nodes.new("LuxCoreNodeVolOutput")
        vol_output.location = 300, 200

        heterogeneous = new_node("LuxCoreNodeVolHeterogeneous", vol_node_tree, vol_output)
        # No scattering
        heterogeneous.inputs["Scattering Scale"].default_value = 0
        heterogeneous.inputs["Scattering"].default_value = (0, 0, 0)
        # Use IOR of air (doesn't really matter)
        heterogeneous.inputs["IOR"].default_value = 1
        # Use smaller absorption depth
        heterogeneous.color_depth = 0.05

        # Absorption (we need to invert it, so we subtract from 1)
        absorption_scale = new_node("LuxCoreNodeTexMath", vol_node_tree, heterogeneous, 0, "Absorption")
        absorption_scale.mode = "subtract"
        absorption_scale.inputs["Value 1"].default_value = 1

        smoke_node = new_node("LuxCoreNodeTexSmoke", vol_node_tree, absorption_scale, 0, "Value 2")
        if is_smoke_domain:
            smoke_node.domain = obj
        smoke_node.source = "density"
        smoke_node.wrap = "black"

        # Emission (fire) - these nodes need to be below the others
        fire_gain = new_node("LuxCoreNodeTexMath", vol_node_tree, heterogeneous, 0, "Emission")
        fire_gain.location.y -= 200
        fire_gain.mode = "scale"
        # Use a high gain value so the fire is visible with the default sky
        fire_gain.inputs["Value 2"].default_value = 100000

        # Colors for the flame
        fire_band = new_node("LuxCoreNodeTexBand", vol_node_tree, fire_gain, 0, "Value 1")
        fire_band.update_add(bpy.context)
        fire_band.update_add(bpy.context)
        fire_band.update_add(bpy.context)
        # Black
        fire_band.items[0].offset = 0
        fire_band.items[0].value = (0, 0, 0)
        # Dark red
        fire_band.items[1].offset = 0.25
        fire_band.items[1].value = (0.35, 0.03, 0)
        # Orange/yellow
        fire_band.items[2].offset = 0.8
        fire_band.items[2].value = (0.9, 0.4, 0)
        # Blue
        fire_band.items[3].offset = 0.95
        fire_band.items[3].value = (0.03, 0.3, 0.8)
        # White
        fire_band.items[4].offset = 1
        fire_band.items[4].value = (1, 1, 1)

        fire_node = new_node("LuxCoreNodeTexSmoke", vol_node_tree, fire_band, 0, "Amount")
        if is_smoke_domain:
            fire_node.domain = obj
        fire_node.source = "fire"
        fire_node.wrap = "black"

        # A smoke material setup only makes sense on the smoke domain object
        if not is_smoke_domain:
            self.report({"ERROR"}, 'Object "%s" is not a smoke domain!' % obj.name)


class LUXCORE_MATERIAL_MT_node_tree_preset(bpy.types.Menu):
    bl_idname = "LUXCORE_MT_node_tree_preset"
    bl_label = "Add Node Tree Preset"
    bl_description = "Add a pre-definied node setup"

    def draw(self, context):
        layout = self.layout
        row = layout.row()

        for category, presets in LUXCORE_OT_preset_material.categories.items():
            col = row.column()
            col.label(category)

            for preset in presets:
                op = col.operator("luxcore.preset_material", text=preset)
                op.preset = preset
