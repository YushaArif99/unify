import requests
from typing import List, Optional

from unify import BASE_URL
from .helpers import _validate_api_key, _res_to_list


def list_providers(
    model: Optional[str] = None, api_key: Optional[str] = None
) -> List[str]:
    """
    Get a list of available providers, either in total or for a specific model.

    Args:
        model: If specified, returns the list of providers supporting this model.
        api_key: If specified, unify API key to be used. Defaults
        to the value in the `UNIFY_KEY` environment variable.

    Returns:
        A list of provider names associated with the model if successful, otherwise an
        empty list.
    Raises:
        BadRequestError: If there was an HTTP error.
        ValueError: If there was an error parsing the JSON response.
    """
    api_key = _validate_api_key(api_key)
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    url = f"{BASE_URL}/providers"
    if model:
        return _res_to_list(requests.get(url, headers=headers, params={"model": model}))
    return _res_to_list(requests.get(url, headers=headers))


def list_models(
    provider: Optional[str] = None, api_key: Optional[str] = None
) -> List[str]:
    """
    Get a list of available models, either in total or for a specific provider.

    Args:
        provider: If specified, returns the list of models supporting this provider.
        api_key: If specified, unify API key to be used. Defaults
        to the value in the `UNIFY_KEY` environment variable.

    Returns:
        A list of available model names if successful, otherwise an empty list.
    Raises:
        BadRequestError: If there was an HTTP error.
        ValueError: If there was an error parsing the JSON response.
    """
    api_key = _validate_api_key(api_key)
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    url = f"{BASE_URL}/models"
    if provider:
        return _res_to_list(
            requests.get(url, headers=headers, params={"provider": provider})
        )
    return _res_to_list(requests.get(url, headers=headers))


def list_endpoints(
    model: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[str]:
    """
    Get a list of available endpoint, either in total or for a specific model or
    provider.

    Args:
        model: If specified, returns the list of endpoint supporting this model.
        provider: If specified, returns the list of endpoint supporting this provider.

        api_key: If specified, unify API key to be used. Defaults to the value in the
        `UNIFY_KEY` environment variable.

    Returns:
        A list of endpoint names if successful, otherwise an empty list.
    Raises:
        BadRequestError: If there was an HTTP error.
        ValueError: If there was an error parsing the JSON response.
    """
    api_key = _validate_api_key(api_key)
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    url = f"{BASE_URL}/endpoints"
    if model and provider:
        raise ValueError("Please specify either model OR provider, not both.")
    elif model:
        return _res_to_list(requests.get(url, headers=headers, params={"model": model}))
    elif provider:
        return _res_to_list(
            requests.get(url, headers=headers, params={"provider": provider})
        )
    return _res_to_list(requests.get(url, headers=headers))
