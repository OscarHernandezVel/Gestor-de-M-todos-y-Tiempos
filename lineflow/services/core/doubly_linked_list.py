from __future__ import annotations

from typing import Any, Dict, Generic, Hashable, Iterator, List, Optional, Set, Tuple, TypeVar

T = TypeVar("T")

__all__ = [
    "Node",
    "DoublyLinkedList",
    "LinkedListError",
    "NodeNotFoundError",
    "DuplicateKeyError",
    "PointerStats",
    "POINTER_STATS",
    "record_pointer_writes",
]


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------
class LinkedListError(Exception):
    """Error genérico de la lista enlazada."""


class NodeNotFoundError(LinkedListError, KeyError):
    """Se solicitó una clave que no existe en la lista."""

    def __str__(self) -> str:  # KeyError agrega comillas; se evita.
        return str(self.args[0]) if self.args else "Node not found"


class DuplicateKeyError(LinkedListError, ValueError):
    """Se intentó insertar una clave que ya existe en la lista."""


# ---------------------------------------------------------------------------
# Instrumentación didáctica
# ---------------------------------------------------------------------------
class PointerStats:
    """Cuenta cuántos punteros se reescriben durante una operación.

    No interviene en la lógica: permite que la interfaz muestre que una
    operación O(1) toca siempre la misma cantidad de punteros sin importar
    el tamaño de la lista. Cuando ``tracking`` está activo también registra
    las claves de los nodos cuyos punteros cambiaron (para animarlos).
    """

    __slots__ = ("writes", "touched", "tracking")

    def __init__(self) -> None:
        self.writes = 0
        self.touched: Set[Hashable] = set()
        self.tracking = False

    def begin(self) -> None:
        """Inicia una medición: reinicia contadores y activa el rastreo."""
        self.writes = 0
        self.touched = set()
        self.tracking = True

    def end(self) -> Tuple[int, Set[Hashable]]:
        """Finaliza la medición y devuelve ``(escrituras, claves_tocadas)``."""
        self.tracking = False
        result = (self.writes, self.touched)
        self.touched = set()
        return result


POINTER_STATS = PointerStats()


def record_pointer_writes(count: int, *nodes: Optional["Node[Any]"]) -> None:
    """Registra ``count`` escrituras de puntero sobre los ``nodes`` indicados."""
    POINTER_STATS.writes += count
    if POINTER_STATS.tracking:
        for node in nodes:
            if node is not None:
                POINTER_STATS.touched.add(node.key)


# ---------------------------------------------------------------------------
# Nodo
# ---------------------------------------------------------------------------
class Node(Generic[T]):
    """Nodo de la lista: dato + punteros ``prev`` y ``next``.

    ``owner`` apunta a la lista que contiene al nodo; permite saber en O(1)
    a qué lista pertenece (útil al trasladar nodos entre listas).
    """

    __slots__ = ("key", "data", "prev", "next", "owner")

    def __init__(self, key: Hashable, data: T) -> None:
        self.key = key
        self.data = data
        self.prev: Optional[Node[T]] = None
        self.next: Optional[Node[T]] = None
        self.owner: Optional[DoublyLinkedList[T]] = None

    @property
    def is_linked(self) -> bool:
        """``True`` si el nodo pertenece actualmente a una lista."""
        return self.owner is not None

    def __repr__(self) -> str:
        prev_key = self.prev.key if self.prev is not None else None
        next_key = self.next.key if self.next is not None else None
        return f"Node({self.key!r}, prev={prev_key!r}, next={next_key!r})"


# ---------------------------------------------------------------------------
# Lista doblemente enlazada
# ---------------------------------------------------------------------------
class DoublyLinkedList(Generic[T]):
    """Lista doblemente enlazada con cursor e índice de localización.

    Parámetros
    ----------
    name:
        Nombre descriptivo (aparece en los mensajes de error).
    context:
        Objeto arbitrario asociado a la lista (p. ej. el dueño de la lista).
    """

    def __init__(self, name: str = "", context: Any = None) -> None:
        self.name = name
        self.context = context
        self.head: Optional[Node[T]] = None
        self.tail: Optional[Node[T]] = None
        self.cursor: Optional[Node[T]] = None
        self._size = 0
        self._index: Dict[Hashable, Node[T]] = {}

    # ------------------------------------------------------------------
    # Primitivas de punteros (núcleo de toda la estructura)
    # ------------------------------------------------------------------
    def _link_between(self, node: Node[T], left: Optional[Node[T]], right: Optional[Node[T]]) -> None:
        """Enlaza ``node`` entre ``left`` y ``right``. O(1), 4 punteros.

        Precondición: ``left.next is right`` (o son los extremos ``None``).

        Antes:  left <-> right
        Después: left <-> node <-> right
        """
        node.prev = left            # 1
        node.next = right           # 2
        if left is None:
            self.head = node        # 3 (node es la nueva cabeza)
        else:
            left.next = node        # 3
        if right is None:
            self.tail = node        # 4 (node es la nueva cola)
        else:
            right.prev = node       # 4
        node.owner = self
        self._index[node.key] = node
        self._size += 1
        record_pointer_writes(4, node, left, right)

    def _detach(self, node: Node[T]) -> Node[T]:
        """Desenlaza ``node`` y une a sus vecinos entre sí. O(1), 4 punteros.

        Antes:  left <-> node <-> right
        Después: left <-> right        (node queda aislado)

        Si el nodo era el cursor, el cursor pasa al sucesor (o al predecesor
        si el nodo era la cola).
        """
        left, right = node.prev, node.next
        if left is None:
            self.head = right       # 1
        else:
            left.next = right       # 1
        if right is None:
            self.tail = left        # 2
        else:
            right.prev = left       # 2
        node.prev = None            # 3
        node.next = None            # 4
        if self.cursor is node:
            self.cursor = right if right is not None else left
        node.owner = None
        del self._index[node.key]
        self._size -= 1
        record_pointer_writes(4, node, left, right)
        return node

    def _require(self, key: Hashable) -> Node[T]:
        try:
            return self._index[key]
        except KeyError:
            label = f" in '{self.name}'" if self.name else ""
            raise NodeNotFoundError(f"'{key}' was not found{label}") from None

    def _new_node(self, key: Hashable, data: T) -> Node[T]:
        if key in self._index:
            raise DuplicateKeyError(f"Key '{key}' already exists in '{self.name}'")
        return Node(key, data)

    def _check_own(self, node: Node[T]) -> None:
        if node.owner is not self:
            raise LinkedListError(f"Node {node.key!r} does not belong to '{self.name}'")

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return self._size

    def __bool__(self) -> bool:
        return self._size > 0

    def __contains__(self, key: object) -> bool:
        return key in self._index

    def __iter__(self) -> Iterator[T]:
        """Recorre los datos de la cabeza a la cola siguiendo ``next``."""
        for node in self.iter_nodes():
            yield node.data

    def __reversed__(self) -> Iterator[T]:
        """Recorre los datos de la cola a la cabeza siguiendo ``prev``."""
        for node in self.iter_nodes_reversed():
            yield node.data

    def __repr__(self) -> str:
        return f"DoublyLinkedList({self.name!r}, [{' <-> '.join(str(k) for k in self.keys())}])"

    def iter_nodes(self) -> Iterator[Node[T]]:
        node = self.head
        while node is not None:
            following = node.next  # se guarda por si el consumidor modifica la lista
            yield node
            node = following

    def iter_nodes_reversed(self) -> Iterator[Node[T]]:
        node = self.tail
        while node is not None:
            preceding = node.prev
            yield node
            node = preceding

    def keys(self) -> List[Hashable]:
        return [node.key for node in self.iter_nodes()]

    def get_node(self, key: Hashable) -> Node[T]:
        """Devuelve el nodo con la clave indicada. O(1)."""
        return self._require(key)

    def find_node(self, key: Hashable) -> Optional[Node[T]]:
        """Como :meth:`get_node` pero devuelve ``None`` si no existe."""
        return self._index.get(key)

    def get(self, key: Hashable) -> T:
        """Devuelve el dato asociado a la clave. O(1)."""
        return self._require(key).data

    @property
    def first(self) -> Optional[T]:
        return self.head.data if self.head is not None else None

    @property
    def last(self) -> Optional[T]:
        return self.tail.data if self.tail is not None else None

    # ------------------------------------------------------------------
    # Inserción
    # ------------------------------------------------------------------
    def append(self, key: Hashable, data: T) -> Node[T]:
        """Inserta al final (después de ``tail``). O(1)."""
        node = self._new_node(key, data)
        self._link_between(node, self.tail, None)
        return node

    def prepend(self, key: Hashable, data: T) -> Node[T]:
        """Inserta al inicio (antes de ``head``). O(1)."""
        node = self._new_node(key, data)
        self._link_between(node, None, self.head)
        return node

    def insert_before(self, ref_key: Hashable, key: Hashable, data: T) -> Node[T]:
        """Inserta un nuevo nodo justo antes de ``ref_key``. O(1)."""
        ref = self._require(ref_key)
        node = self._new_node(key, data)
        self._link_between(node, ref.prev, ref)
        return node

    def insert_after(self, ref_key: Hashable, key: Hashable, data: T) -> Node[T]:
        """Inserta un nuevo nodo justo después de ``ref_key``. O(1)."""
        ref = self._require(ref_key)
        node = self._new_node(key, data)
        self._link_between(node, ref, ref.next)
        return node

    def insert_at(self, key: Hashable, data: T, before_key: Optional[Hashable] = None) -> Node[T]:
        """Inserta antes de ``before_key``; si es ``None`` inserta al final."""
        if before_key is None:
            return self.append(key, data)
        return self.insert_before(before_key, key, data)

    def insert_node_between(self, node: Node[T], left: Optional[Node[T]], right: Optional[Node[T]]) -> Node[T]:
        """Enlaza un nodo *ya creado* entre dos vecinos contiguos. O(1).

        Útil para estructuras que calculan sus propios puntos de anclaje
        (por ejemplo, los segmentos de estación en la línea de ensamble).
        """
        if node.owner is not None:
            raise LinkedListError(f"Node {node.key!r} is already linked")
        if node.key in self._index:
            raise DuplicateKeyError(f"Key '{node.key}' already exists in '{self.name}'")
        expected_right = left.next if left is not None else self.head
        if expected_right is not right:
            raise LinkedListError("left and right must be adjacent nodes")
        self._link_between(node, left, right)
        return node

    def detach_node(self, node: Node[T]) -> Node[T]:
        """Desenlaza un nodo de esta lista (recibido por referencia). O(1)."""
        self._check_own(node)
        return self._detach(node)

    # ------------------------------------------------------------------
    # Eliminación
    # ------------------------------------------------------------------
    def remove(self, key: Hashable) -> T:
        """Elimina el nodo con la clave y devuelve su dato. O(1)."""
        return self._detach(self._require(key)).data

    def pop_front(self) -> Node[T]:
        if self.head is None:
            raise LinkedListError(f"'{self.name}' is empty")
        return self._detach(self.head)

    def pop_back(self) -> Node[T]:
        if self.tail is None:
            raise LinkedListError(f"'{self.name}' is empty")
        return self._detach(self.tail)

    def clear(self) -> None:
        """Vacía la lista rompiendo todos los enlaces. O(n)."""
        node = self.head
        while node is not None:
            following = node.next
            node.prev = node.next = None
            node.owner = None
            node = following
        self.head = self.tail = self.cursor = None
        self._index = {}
        self._size = 0

    # ------------------------------------------------------------------
    # Reordenamiento
    # ------------------------------------------------------------------
    def move(self, key: Hashable, before_key: Optional[Hashable] = None) -> Node[T]:
        """Reubica ``key`` justo antes de ``before_key`` (al final si es ``None``).

        Se desenlaza el nodo (4 punteros) y se vuelve a enlazar en su nuevo
        lugar (4 punteros): O(1). El cursor se conserva si apuntaba al nodo.
        """
        node = self._require(key)
        if before_key == key:
            return node
        ref = self._require(before_key) if before_key is not None else None
        if node.next is ref:  # ya está en esa posición
            return node
        was_cursor = self.cursor is node
        self._detach(node)
        left = ref.prev if ref is not None else self.tail
        self._link_between(node, left, ref)
        if was_cursor:
            self.cursor = node
        return node

    def move_after(self, key: Hashable, after_key: Hashable) -> Node[T]:
        """Reubica ``key`` justo después de ``after_key``. O(1)."""
        ref = self._require(after_key)
        if after_key == key:
            return ref
        following = ref.next
        return self.move(key, following.key if following is not None else None)

    def move_to_front(self, key: Hashable) -> Node[T]:
        node = self._require(key)
        if self.head is node:
            return node
        return self.move(key, self.head.key if self.head is not None else None)

    def move_to_back(self, key: Hashable) -> Node[T]:
        return self.move(key, None)

    def transfer(self, key: Hashable, target: "DoublyLinkedList[T]", before_key: Optional[Hashable] = None) -> Node[T]:
        """Traslada el nodo a *otra* lista, antes de ``before_key``. O(1).

        Se valida todo antes de tocar punteros para que un error no deje
        el nodo "perdido" fuera de ambas listas.
        """
        if target is self:
            return self.move(key, before_key)
        node = self._require(key)
        if node.key in target._index:
            raise DuplicateKeyError(f"Key '{key}' already exists in '{target.name}'")
        ref = target._require(before_key) if before_key is not None else None
        self._detach(node)
        left = ref.prev if ref is not None else target.tail
        target._link_between(node, left, ref)
        return node

    def move_segment(self, first: Node[T], last: Node[T], after: Optional[Node[T]]) -> bool:
        """Mueve el segmento contiguo ``first..last`` para que quede después de ``after``.

        Si ``after`` es ``None`` el segmento pasa al inicio de la lista. Solo
        se reescriben los punteros de los bordes (8 en total); los nodos
        internos del segmento no se tocan, por lo que la operación es O(1)
        sin importar la longitud del segmento. ``after`` no debe pertenecer
        al segmento. Devuelve ``False`` si el segmento ya estaba en su lugar.
        """
        self._check_own(first)
        self._check_own(last)
        if after is not None:
            self._check_own(after)
        current_left = first.prev
        if current_left is after:
            return False
        # 1) Desenlazar el segmento: sus vecinos externos se unen entre sí.
        left, right = first.prev, last.next
        if left is None:
            self.head = right
        else:
            left.next = right
        if right is None:
            self.tail = left
        else:
            right.prev = left
        first.prev = None
        last.next = None
        record_pointer_writes(4, first, last, left, right)
        # 2) Enlazar el segmento en su nueva posición.
        new_right = after.next if after is not None else self.head
        first.prev = after
        last.next = new_right
        if after is None:
            self.head = first
        else:
            after.next = first
        if new_right is None:
            self.tail = last
        else:
            new_right.prev = last
        record_pointer_writes(4, first, last, after, new_right)
        return True

    # ------------------------------------------------------------------
    # Cursor (nodo activo)
    # ------------------------------------------------------------------
    def set_cursor(self, key: Hashable) -> Node[T]:
        self.cursor = self._require(key)
        return self.cursor

    def clear_cursor(self) -> None:
        self.cursor = None

    def cursor_next(self, wrap: bool = False) -> Tuple[Optional[Node[T]], bool]:
        """Avanza el cursor por el puntero ``next``. O(1).

        Devuelve ``(nodo, dio_la_vuelta)``. Con ``wrap=True`` al pasar de la
        cola regresa a la cabeza (nuevo ciclo); si no, se queda en la cola.
        """
        if self.cursor is None:
            self.cursor = self.head
            return self.cursor, False
        if self.cursor.next is not None:
            self.cursor = self.cursor.next
            return self.cursor, False
        if wrap and self.head is not None:
            self.cursor = self.head
            return self.cursor, True
        return self.cursor, False

    def cursor_prev(self, wrap: bool = False) -> Tuple[Optional[Node[T]], bool]:
        """Retrocede el cursor por el puntero ``prev``. O(1)."""
        if self.cursor is None:
            self.cursor = self.tail
            return self.cursor, False
        if self.cursor.prev is not None:
            self.cursor = self.cursor.prev
            return self.cursor, False
        if wrap and self.tail is not None:
            self.cursor = self.tail
            return self.cursor, True
        return self.cursor, False

    def cursor_to_head(self) -> Optional[Node[T]]:
        self.cursor = self.head
        return self.cursor

    def cursor_to_tail(self) -> Optional[Node[T]]:
        self.cursor = self.tail
        return self.cursor

    # ------------------------------------------------------------------
    # Integridad
    # ------------------------------------------------------------------
    def validate(self) -> None:
        """Verifica todas las invariantes de punteros. O(n).

        Lanza :class:`LinkedListError` si encuentra una inconsistencia. Se usa
        en las pruebas automáticas después de cada operación.
        """
        if self.head is not None and self.head.prev is not None:
            raise LinkedListError("head.prev must be None")
        if self.tail is not None and self.tail.next is not None:
            raise LinkedListError("tail.next must be None")
        if (self.head is None) != (self.tail is None):
            raise LinkedListError("head and tail must be both None or both set")
        count = 0
        previous: Optional[Node[T]] = None
        node = self.head
        while node is not None:
            if node.prev is not previous:
                raise LinkedListError(f"Broken prev pointer at {node.key!r}")
            if node.owner is not self:
                raise LinkedListError(f"Wrong owner at {node.key!r}")
            if self._index.get(node.key) is not node:
                raise LinkedListError(f"Index mismatch at {node.key!r}")
            count += 1
            if count > self._size:
                raise LinkedListError("Cycle detected or size too small")
            previous = node
            node = node.next
        if previous is not self.tail:
            raise LinkedListError("Tail does not match the last reachable node")
        if count != self._size or len(self._index) != self._size:
            raise LinkedListError(f"Size mismatch: walked={count} size={self._size} index={len(self._index)}")
        if self.cursor is not None and self.cursor.owner is not self:
            raise LinkedListError("Cursor points outside the list")
