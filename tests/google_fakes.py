"""Imitação mínima do encadeamento do googleapiclient: service.users().messages().list(...).execute()."""


class _Call:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result() if callable(self._result) else self._result


class FakeResource:
    """Cada atributo vira um sub-recurso; métodos folha devolvem respostas configuradas e gravam kwargs."""

    def __init__(self, responses, calls, path=""):
        self._responses = responses
        self._calls = calls
        self._path = path

    def __getattr__(self, name):
        path = f"{self._path}.{name}" if self._path else name

        def method(*args, **kwargs):
            if path in self._responses:
                self._calls.append((path, kwargs))
                resp = self._responses[path]
                return _Call(lambda: resp(**kwargs) if callable(resp) else resp)
            return FakeResource(self._responses, self._calls, path)

        return method


def fake_service(responses):
    calls = []
    return FakeResource(responses, calls), calls
