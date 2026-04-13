with open('/Users/greggcochran/copilot-cli-agent-pulse/site/index.html', 'r') as f:
    content = f.read()

start_marker = "  /* \u2500\u2500 Terminal Demo Animation \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */"
end_marker = "  demObs.observe(document.getElementById('demo'));"

si = content.find(start_marker)
ei = content.find(end_marker) + len(end_marker)
print(f"Found JS section: {si} to {ei}")

with open('/Users/greggcochran/copilot-cli-agent-pulse/site/index.html', 'w') as f:
    f.write(content[:si])
    f.write("PLACEHOLDER_JS_SECTION")
    f.write(content[ei:])
print("Placeholder written")
