# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from argparse import BooleanOptionalAction

from django_utils.workers.command import ChannelCeleryCommand


class Command(ChannelCeleryCommand):
    def add_arguments(self, parser):
        parser.add_argument("--product_id", type=str, help="Product SKU")
        self.default_arguments.append("product_id")
        parser.add_argument("--bulk", type=bool, action=BooleanOptionalAction, help="Run Bulk", default=True)
        self.default_arguments.append("bulk")
        parser.add_argument(
            "--picture_roles",
            type=str,
            nargs="*",
            help="Media types. Allowed values: main,general,unknown,variant,angle",
            default=["main", "general"],
        )
        self.default_arguments.append("picture_roles")
        super().add_arguments(parser)
