"""Engines for the VMware to Azure migration decision simulator.

Present so that ``core`` is a regular package rather than an implicit namespace
package. Under a module reloader -- Streamlit's included -- regular packages
behave more predictably, and the modules here are imported by the Streamlit
pages on every rerun.

Deliberately empty of imports: importing submodules here would force the whole
dependency graph (and every live pricing client) to load even when a page needs
only one module.
"""
