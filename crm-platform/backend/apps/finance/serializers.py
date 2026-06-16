from rest_framework import serializers
from .models import Account, Category, Transaction


class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ["id", "name", "kind", "is_active", "balance"]

    def get_balance(self, obj):
        return obj.balance()


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "direction"]


class TransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Transaction
        fields = ["id", "direction", "amount", "account", "account_name",
                  "category", "category_name", "comment", "deal", "date", "created_at"]
