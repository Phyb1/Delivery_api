from django.core.management.base import BaseCommand

from apps.integrations import webhooks


class Command(BaseCommand):
    help = "Send pending webhook events. Run on a schedule (cron, systemd timer, EventBridge)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100, help="Maximum events per run.")

    def handle(self, *args, **options):
        sent = webhooks.process_pending(limit=options["limit"])
        self.stdout.write(f"Sent {sent} webhook event(s).")
