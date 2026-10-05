"""Check every MJCF include and mesh/texture reference without starting a robot."""
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]

def check_resources(root=ROOT):
    issues=[]
    for scene in sorted((root/'assets/scenes').glob('*/scene.xml')):
        tree=ET.parse(scene);compiler=tree.find('compiler'); attrs=compiler.attrib if compiler is not None else {}
        for node in tree.iter():
            name=node.get('file')
            if not name:continue
            prefix=attrs.get('meshdir','') if node.tag=='mesh' else attrs.get('texturedir','') if node.tag=='texture' else ''
            target=(scene.parent/prefix/name).resolve()
            if not target.is_relative_to(root):issues.append(f'{scene.parent.name}: resource outside release: {name}')
            elif not target.exists():issues.append(f'{scene.parent.name}: missing {name}')
    return issues
