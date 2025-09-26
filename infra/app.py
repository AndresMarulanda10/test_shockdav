#!/usr/bin/env python3
"""CDK app entry point.

This file bootstraps the CDK application and instantiates the
`BitgetStack` defined in `infra/bitget_stack.py`.
"""

from aws_cdk import App
from infra.bitget_stack import BitgetStack

app = App()
BitgetStack(app, "BitgetStack")
app.synth()
