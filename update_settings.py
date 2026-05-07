
import os

filepath = 'config/settings.py'
with open(filepath, 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    new_lines.append(line)
    if "'RESOURCE_TYPE': 'auto'," in line:
        new_lines.append("    'PRESERVE_EXTENSIONS': True,\n")

with open(filepath, 'w') as f:
    f.writelines(new_lines)
