from django.core.management.base import BaseCommand
from leaves.services import run_monthly_accrual, run_carry_forward

class Command(BaseCommand):
    help = 'Runs leave accrual and carry forward processes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=['accrual', 'carry_forward', 'initialize'],
            help='Type of process to run: "accrual", "carry_forward", or "initialize" for existing users'
        )

    def handle(self, *args, **options):
        process_type = options['type']

        if process_type == 'accrual':
            self.stdout.write("Running monthly accrual...")
            try:
                run_monthly_accrual()
                self.stdout.write(self.style.SUCCESS("Successfully ran monthly accruals"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error running accruals: {str(e)}"))

        elif process_type == 'carry_forward':
            self.stdout.write("Running carry forward process...")
            try:
                run_carry_forward()
                self.stdout.write(self.style.SUCCESS("Successfully ran carry forward"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error running carry forward: {str(e)}"))

        elif process_type == 'initialize':
            self.stdout.write("Initializing balances for all active users...")
            from users.models import CustomUser
            from leaves.services import initialize_user_leave_balances
            
            users = CustomUser.objects.filter(is_active=True)
            count = 0
            for user in users:
                try:
                    initialize_user_leave_balances(user)
                    count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error initializing for {user}: {str(e)}"))
            
            self.stdout.write(self.style.SUCCESS(f"Successfully initialized balances for {count} users"))

        else:
            self.stdout.write(self.style.WARNING("Please specify --type accrual, --type carry_forward, or --type initialize"))
