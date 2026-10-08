"""Status action text: the verb that leads to the status (see setup/install.py)."""


def execute():
	from renpos.setup.install import set_default_process_status
	set_default_process_status()
