from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0003_alter_crisisassessmentrecord_provider'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='crisisassessmentrecord',
            name='classifier_flagged',
        ),
        migrations.RemoveField(
            model_name='crisisassessmentrecord',
            name='classifier_categories',
        ),
    ]
