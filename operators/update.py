import requests
from requests import ConnectionError
import json
import platform
from collections import OrderedDict

import bpy
from bpy.props import StringProperty, EnumProperty
from ..bin import pyluxcore

GITHUB_API_RELEASE_URL = "https://api.github.com/repos/LuxCoreRender/BlendLuxCore/releases"


class Release:
    # E.g. "v2.0alpha7"
    version_string = ""
    # if it is an unstable (alpha/beta) version
    is_prerelease = False
    download_url = ""


releases = OrderedDict()


def get_current_version():
    from .. import bl_info
    version = bl_info["version"]
    # Major.minor version, e.g. "v2.0"
    version_string = "v%d.%d" % (version[0], version[1])
    # alpha/beta suffix, e.g. "alpha7"
    version_string += bl_info["warning"]
    return version_string


def release_items_callback(scene, context):
    print("callback called")
    items = []
    current_version = get_current_version()

    for i, release in enumerate(releases.values()):
        description = ""
        version_string = release.version_string

        if version_string == current_version:
            # A green checkmark to signal the currently installed version
            icon = "FILE_TICK"
            description += " (installed)"
        elif release.is_prerelease:
            icon = "ERROR"
            description += " (unstable)"
        else:
            icon = "NONE"

        items.append((version_string, version_string, description, icon, i))

    return items


class LUXCORE_OT_change_version(bpy.types.Operator):
    bl_idname = "luxcore.change_version"
    bl_label = "Change Version"
    bl_description = "Download a different BlendLuxCore version and replace this installation"

    selected_release = EnumProperty(name="Releases", items=release_items_callback,
                                    description="Select a release")

    def invoke(self, context, event):
        """
        The evoke method fetches the current list of releases from GitHub
        and shows a popup dialog with a dropdown list of versions to the user.
        """
        releases.clear()

        try:
            response_raw = requests.get(GITHUB_API_RELEASE_URL)
        except ConnectionError as error:
            self.report({"ERROR"}, "Connection error")
            return {"CANCELLED"}

        if not response_raw.ok:
            self.report({"ERROR"}, "Response not ok")
            return {"CANCELLED"}

        response = json.loads(response_raw.text or response_raw.content)

        # Info about the currently installed version
        current_is_opencl = not pyluxcore.GetPlatformDesc().Get("compile.LUXRAYS_DISABLE_OPENCL").GetBool()
        system_mapping = {
            "Linux": "linux64",
            "Windows": "win64",
        }
        try:
            current_system = system_mapping[platform.system()]
        except KeyError:
            self.report({"ERROR"}, "Unsupported system: " + platform.system())
            return {"CANCELLED"}

        for release_info in response:
            entry = Release()
            entry.version_string = release_info["name"].replace("BlendLuxCore ", "")
            entry.is_prerelease = release_info["prerelease"]

            # Assets are the different .zip packages for various OS, with/without OpenCL etc.
            for asset in release_info["assets"]:
                # The name has the form
                # "BlendLuxCore-v2.0alpha7-linux64-opencl.zip" or
                # "BlendLuxCore-v2.0alpha7-linux64.zip" (non-opencl builds)
                middle = asset["name"].replace("BlendLuxCore-", "").replace(".zip", "")
                parts = middle.split("-")
                if len(parts) == 2:
                    version, system = parts
                    is_opencl = False
                elif len(parts) == 3:
                    version, system, _ = parts
                    is_opencl = True
                else:
                    # Older alpha releases used a different naming scheme, we don't support them
                    continue

                if system == current_system and is_opencl == current_is_opencl:
                    # Found the right asset
                    entry.download_url = asset["browser_download_url"]
                    break

            # The asset finding loop may skip entries with old naming scheme, don't include those
            if entry.download_url:
                releases[entry.version_string] = entry

        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def execute(self, context):
        """
        The execute method is called when the user clicks the "OK" button.
        It downloads and installs the requested version.
        """
        print(self.selected_release)
        requested_release = releases[self.selected_release]

        if requested_release.version_string == get_current_version():
            self.report({"ERROR"}, "This is the currently installed version")
            return {"CANCELLED"}

        self.report({"INFO"}, "Downloading version " + requested_release.version_string)

        # TODO download and replace

        return {"FINISHED"}