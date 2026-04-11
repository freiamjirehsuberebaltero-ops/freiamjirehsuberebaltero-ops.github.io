import os
import zipfile
import json
import re

MODS_PATH = r"C:\Users\Freiam\AppData\Roaming\.minecraft\mods"

def clean_version(version, filename):
    """If version is a placeholder like ${file.jarVersion}, try to extract it from filename."""
    if version and ("${" in version or version == "N/A"):
        # Regex to find something that looks like a version (e.g., 1.20.1-1.2.3 or 4.5.6)
        match = re.search(r'(\d+\.\d+(?:\.\d+)?(?:[\-\w\.]+))', filename)
        if match:
            return match.group(1)
    return version

def get_mod_details(jar_path):
    name = "Unknown"
    version = "N/A"
    filename = os.path.basename(jar_path)
    
    try:
        with zipfile.ZipFile(jar_path, 'r') as jar:
            # 1. Try Fabric
            if 'fabric.mod.json' in jar.namelist():
                with jar.open('fabric.mod.json') as f:
                    data = json.load(f, strict=False)
                    name = data.get('name', name)
                    version = data.get('version', version)
            
            # 2. Try Forge (Modern)
            elif 'META-INF/mods.toml' in jar.namelist():
                with jar.open('META-INF/mods.toml') as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    name_match = re.search(r'displayName\s*=\s*"(.*?)"', content)
                    version_match = re.search(r'version\s*=\s*"(.*?)"', content)
                    if name_match: name = name_match.group(1)
                    if version_match: version = version_match.group(1)
            
            # 3. Try Legacy Forge
            elif 'mcmod.info' in jar.namelist():
                with jar.open('mcmod.info') as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    # Clean up common json errors in mcmod.info
                    data = json.loads(re.sub(r',\s*([\]}])', r'\1', content))
                    if isinstance(data, list) and len(data) > 0:
                        name = data[0].get('name', name)
                        version = data[0].get('version', version)

            # 4. Final fix: If version is still a placeholder, check MANIFEST.MF
            if "${" in version or version == "N/A":
                if 'META-INF/MANIFEST.MF' in jar.namelist():
                    with jar.open('META-INF/MANIFEST.MF') as f:
                        for line in f:
                            line_str = line.decode('utf-8', errors='ignore')
                            if "Implementation-Version:" in line_str:
                                version = line_str.split(":", 1)[1].strip()
                                break

    except Exception:
        name = filename

    # Run the version cleaner if we got a placeholder
    version = clean_version(version, filename)
    
    return name, version

def main():
    if not os.path.exists(MODS_PATH):
        print(f"Error: Path not found: {MODS_PATH}")
        return

    # Header
    print(f"{'Name':<35} | {'Version':<20} | {'Size':<10}")
    print("-" * 70)

    # Sort files alphabetically
    files = [f for f in os.listdir(MODS_PATH) if f.endswith(".jar")]
    files.sort()

    for file in files:
        full_path = os.path.join(MODS_PATH, file)
        size_mb = f"{os.path.getsize(full_path) / (1024 * 1024):.2f} MB"
        name, version = get_mod_details(full_path)
        
        # Trim names that are too long for the table
        display_name = (name[:32] + '..') if len(name) > 34 else name
        display_version = (version[:18] + '..') if len(version) > 20 else version
        
        print(f"{display_name:<35} | {display_version:<20} | {size_mb:<10}")

if __name__ == "__main__":
    main()