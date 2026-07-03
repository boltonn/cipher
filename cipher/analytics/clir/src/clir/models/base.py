from abc import ABC, abstractmethod


class Model(ABC):
    @abstractmethod
    def load(self):
        """Load the model into memory."""
        raise NotImplementedError

    @abstractmethod
    def unload(self):
        """Unload the model from memory."""
        raise NotImplementedError

    @abstractmethod
    def infer(self):
        """Perform inference using the model."""
        raise NotImplementedError
