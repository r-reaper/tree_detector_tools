def classFactory(iface):
    from .tree_detector_tools import TreeDetectorPlugin
    return TreeDetectorPlugin(iface)