from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Пагинация с выбором размера страницы: ?page_size=5..500 (по умолч. 50)."""
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500
