import pathlib
import hypothesis


def filepaths(depth=2):
    """Strategy for generating filepaths"""
    part = hypothesis.strategies.text(
        alphabet=hypothesis.strategies.characters(
            whitelist_categories=['Ll']
        )
    )
    parts = [part for i in range(depth)]
    def to_path(*parts):
        path = os.path.join(*parts)
        return pathlib.Path(path)
    return hypothesis.strategies.builds(to_path, *parts)