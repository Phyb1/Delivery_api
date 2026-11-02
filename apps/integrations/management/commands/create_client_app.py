from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from apps.integrations.models import ClientApp


class Command(BaseCommand):
    help = "Register another project as an API client and print its API key (shown once)."

    def add_arguments(self, parser):
        parser.add_argument("name", help="Unique name for the client app.")
        parser.add_argument("--webhook-url", default="", help="Where to send delivery updates.")

    def handle(self, *args, **options):
        try:
            app, raw_key = ClientApp.issue(name=options["name"], webhook_url=options["webhook_url"])
        except IntegrityError as exc:
            raise CommandError(f"A client app named '{options['name']}' already exists.") from exc

        self.stdout.write(self.style.SUCCESS(f"Created client app '{app.name}'."))
        self.stdout.write(f"API key (store it now, it is not shown again): {raw_key}")
        self.stdout.write(f"Webhook signing secret: {app.webhook_secret}")
