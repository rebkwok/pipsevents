from unittest.mock import Mock


def get_mock_request(user):
    mock_request = Mock()
    mock_request.build_absolute_uri = Mock(return_value="https://test.test")
    mock_request.user = user
    return mock_request
