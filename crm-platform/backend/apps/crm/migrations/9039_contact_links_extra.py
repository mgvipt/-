from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "9038_contact_multi_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="contact",
            name="links_extra",
            field=models.JSONField(
                "\u0414\u043e\u0434\u0430\u0442\u043a\u043e\u0432\u0456 \u043f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f \u043d\u0430 \u0430\u043a\u0430\u0443\u043d\u0442\u0438",
                blank=True, default=list,
                help_text="[{label,value}] \u2014 \u043a\u0456\u043b\u044c\u043a\u0430 \u043f\u043e\u0441\u0438\u043b\u0430\u043d\u044c",
            ),
        ),
    ]
