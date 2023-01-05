# chessgraph

An utility to create a graph of moves from a specified position.

For example:

!(Spanish)[spanish.svg]

This image was generated using:

```bash
python chessgraph.py  --depth=10 --alpha=-20 --beta=0 --position="r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3" > spanish.dot
dot -Tsvg spanish.dot -o spanish.svg
```

The svg image contains links to the online [Chess Cloud Database](https://chessdb.cn/queryc_en/) that is queried to generate the graph.
As this database is continuously updated, generated graphs will be a snapshot of the database state at the time of creation.

To use this tool [graphviz](https://graphviz.org/) must be available to convert the `.dot` file to an image format such as `.svg` or `.png`.
Whereas the former can have embedded links to latter might be more convient to share and modify. Generate a high-resolution version as:

```bash
dot -Tpng -Gdpi=300 spanish.dot -o spanish.png
```

!(Spanish)[spanish.png]
