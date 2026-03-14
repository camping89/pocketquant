# Research: Python Dependency & Architecture Visualization Tools

**Date:** 2026-03-14 | **Evaluated:** VS Code extensions + CLI tools for Python projects

---

## Executive Summary

For visualizing Python project dependencies in VS Code:
- **No single perfect solution exists**
- Best approach: **hybrid** (VS Code extension for basic visualization + CLI tools for detailed analysis)
- Dependency Cruiser is **JS-only** (doesn't support Python)
- Python-specific tooling fragmented between module dependencies vs. call graphs

---

## VS Code Extensions (Python Support)

| Extension                                 | Python Support        | Graph Types                     | VS Code Integration | Auto-Update | Status     |
|-------------------------------------------|-----------------------|---------------------------------|---------------------|-------------|------------|
| **Code Dependency Visualizer**            | ✅ Yes                 | Import/Dependency graphs        | Good                | Yes         | Active     |
| **CodeVisualizer**                        | ✅ Yes                 | Dependency + Call flow          | Good                | Yes         | Active     |
| **CodeBaseRelationshipVisualizer (CBRV)** | ✅ Yes                 | File dependencies + call stacks | Good                | Manual      | Active     |
| **Code Graph (CodeAtlas)**                | ✅ Yes (C++/C#/Python) | Call graph + inheritance        | Good                | Auto        | Active     |
| **Call Graph**                            | ⚠️ Limited             | Function call graphs            | Fair                | Manual      | Maintained |
| **Dependency Graph**                      | ⚠️ Limited             | Basic dependencies              | Fair                | Manual      | Maintained |
| **DepViz**                                | ✅ Yes                 | Architecture diagrams           | Good                | Auto        | Active     |
| **Crabviz**                               | ⚠️ Limited             | Call graphs (LSP-based)         | Good                | Auto        | Active     |

**Winner for VS Code:** **CodeVisualizer** or **DepViz** - both handle dependency graphs + Python natively.

---

## Dependency Cruiser

- **Python Support:** ❌ **NO** - JS/TS/CoffeeScript only
- **Graph Types:** Dependency analysis, circular dependencies
- **Verdict:** Not viable for Python projects
- **Source:** Official docs confirm language support limited to JavaScript ecosystem

---

## Pyreverse (Pylint Built-In)

| Aspect                  | Details                                                              |
|-------------------------|----------------------------------------------------------------------|
| **Python Support**      | ✅ Yes - generates UML diagrams                                       |
| **Graph Generation**    | ✅ Class/package diagrams from AST                                    |
| **Output Format**       | `.gv` (Graphviz dot files)                                           |
| **VS Code Integration** | ⚠️ CLI-only, no native extension                                      |
| **Workflow**            | `pyreverse mypackage/` → generates .gv → requires Graphviz to render |
| **Limitations**         | UML-focused (classes/inheritance), not module imports                |
| **Ideal For**           | Architecture documentation, class relationships                      |

**Drawback:** Requires manual Graphviz rendering; not live/auto-updating in VS Code.

---

## Python Call Graph

| Aspect                  | Details                                                |
|-------------------------|--------------------------------------------------------|
| **Python Support**      | ✅ Yes - runtime call tracing                           |
| **Graph Types**         | Function call graphs (not import graphs)               |
| **CLI Usage**           | `pycallgraph --output_file=graph.svg myapp.py`         |
| **Output**              | SVG, PNG, JSON, GDF (Gephi format)                     |
| **VS Code Integration** | ⚠️ No extension; CLI + manual visualization             |
| **Auto-Update**         | ❌ No - static snapshot of runtime                      |
| **Library**             | pycallgraph2 (latest), original pycallgraph (archived) |
| **Version**             | 2.1.6 (supports Python 3.8-3.13)                       |
| **Use Case**            | Debug function flows, identify bottlenecks             |

**Best For:** Understanding program execution flow, not static module structure.

---

## CLI Tools: Dependency Analysis & Mermaid Generation

### **pydeps** (Module Dependency Visualizer)

| Aspect             | Details                                         |
|--------------------|-------------------------------------------------|
| **Python Support** | ✅ Yes                                           |
| **Graph Types**    | Module imports, circular dependency detection   |
| **CLI**            | `pydeps mypackage --max-bacon=2`                |
| **Output**         | SVG (interactive with hover), PNG, Graphviz dot |
| **Auto-Update**    | ❌ Manual CLI re-runs                            |
| **Graphviz Req**   | ✅ Required (dot command)                        |
| **Filtering**      | `--max-bacon`, `--max-module-depth`             |
| **Source**         | https://github.com/thebjorn/pydeps              |

**Strengths:** Specifically built for Python module dependencies, handles cycles, lightweight.

### **Mermaid-based Tools**

| Tool            | Purpose                                                               | Status        |
|-----------------|-----------------------------------------------------------------------|---------------|
| **mermaid-py**  | Python library to generate Mermaid diagrams programmatically          | ✅ Active      |
| **mermaid-cli** | CLI to render `.mmd` files to SVG/PNG                                 | ✅ Active      |
| **pymermaider** | Rust-based tool: Python code → Mermaid class diagrams (auto-analysis) | ⚠️ Specialized |
| **mmdc**        | Offline Mermaid converter (no browser/Node.js needed)                 | ✅ Active      |

**Note:** No off-the-shelf tool that directly converts Python imports → Mermaid graph. Would require custom script.

---

## Recommendation Matrix

### Use Case 1: **Real-Time VS Code Visualization**
**Recommendation:** **CodeVisualizer** or **DepViz**
- Native Python support
- Auto-updating dependency graphs
- Integrated into IDE
- Interactive exploration

### Use Case 2: **Detailed Module Import Analysis (CLI)**
**Recommendation:** **pydeps**
- Fast, Python-specific
- Circular dependency detection
- Lightweight (no heavy IDE overhead)
- Command: `pydeps src/ --max-bacon=2 --output=svg`

### Use Case 3: **Architecture & Class Relationships**
**Recommendation:** **Pyreverse** (CLI) + rendering
- UML diagrams (classes, inheritance)
- Built into pylint (no extra install)
- Command: `pyreverse -o png mypackage/`

### Use Case 4: **Function Call Tracing**
**Recommendation:** **pycallgraph2** (CLI)
- Runtime flow analysis
- Useful for performance debugging
- Command: `pycallgraph --output_file=graph.svg myapp.py`

### Use Case 5: **Custom Mermaid Diagrams**
**Recommendation:** Write custom Python script using **mermaid-py**
- Parse imports with `ast` module
- Generate Mermaid syntax
- Render with **mermaid-cli**

---

## Unresolved Questions

1. Does CodeVisualizer auto-update when files change, or requires manual refresh?
2. Can CBRV handle large Python projects (1000+ files) without performance degradation?
3. Are there any VS Code extensions combining pydeps + live rendering?
4. What's the best practice for integrating Mermaid generation into GitHub Actions CI/CD?

---

## Sources

- [Code Dependency Visualizer - VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=artinmajdi.code-dependency-visualizer)
- [CodeVisualizer - GitHub](https://github.com/syntax-syndicate/CodeVisualizer-vsce)
- [Dependency Cruiser - GitHub](https://github.com/sverweij/dependency-cruiser)
- [Pyreverse - Pylint Documentation](https://pylint.readthedocs.io/en/stable/pyreverse.html)
- [pycallgraph - PyPI](https://pypi.org/project/python-call-graph/)
- [pydeps - GitHub](https://github.com/thebjorn/pydeps)
- [pydeps - Documentation](https://pydeps.readthedocs.io/)
- [mermaid-py - PyPI](https://pypi.org/project/mermaid-py/)
- [mermaid-cli - PyPI](https://pypi.org/project/mermaid-cli/)
- [pymermaider - GitHub](https://github.com/diceroll123/pymermaider)
- [DepViz - VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=Zentch.depviz)
- [CodeBaseRelationshipVisualizer - GitHub](https://github.com/jesse-r-s-hines/CodeBaseRelationshipVisualizer)
