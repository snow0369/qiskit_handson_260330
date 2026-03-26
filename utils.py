import json
from qiskit.quantum_info import SparsePauliOp


def load_sparse_pauli_ops_from_pickle(
    filename: str,
    reverse_pauli_strings: bool = True,
    simplify: bool = True,
):
    """
    Read a json file of the form

        {
            "H2": {
                "pauli_strings": ["XXII", "IZZI", ...],
                "coefficients": [0.1, -0.2, ...]
            },
            "H4": {...},
            ...
        }

    and return

        {
            "H2": SparsePauliOp(...),
            "H4": SparsePauliOp(...),
            ...
        }

    Parameters
    ----------
    filename : str
        Path to the JSON file.
    reverse_pauli_strings : bool
        Set True if the stored strings use qubit-0 on the LEFT.
        Qiskit expects qubit-0 on the RIGHT.
    simplify : bool
        If True, combine duplicate Pauli terms and remove zeros.

    Returns
    -------
    dict[str, SparsePauliOp]
    """
    with open(filename, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    out = {}

    for mol_name, data in raw_data.items():
        pauli_strings = data["pauli_strings"]
        coeffs = data["coefficients"]
        if len(pauli_strings) != len(coeffs):
            raise ValueError(
                f"{mol_name}: number of Pauli strings ({len(pauli_strings)}) "
                f"!= number of coefficients ({len(coeffs)})"
            )

        qiskit_strings = [
            s[::-1] if reverse_pauli_strings else s
            for s in pauli_strings
        ]
        parsed_coeffs = [
            complex(c["real"], c["imag"]) if isinstance(c, dict) else c
            for c in coeffs
        ]
        op = SparsePauliOp.from_list(list(zip(qiskit_strings, parsed_coeffs)))

        if simplify:
            op = op.simplify()

        out[mol_name] = op

    return out
