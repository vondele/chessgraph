import requests
import pickle
import platform
import argparse
import chess
import chess.engine
import chess.svg
import math
import sys
import concurrent.futures
import multiprocessing
import copy
import hashlib
import cairosvg
import graphviz
from os.path import exists
from urllib import parse


class ChessGraph:
    def __init__(
        self,
        networkstyle,
        depth,
        concurrency,
        source,
        lichessdb,
        engine,
        enginedepth,
        enginemaxmoves,
        boardstyle,
        boardedges,
    ):
        self.networkstyle = networkstyle
        self.depth = depth
        self.source = source
        self.lichessdb = lichessdb
        self.engine = engine
        self.enginedepth = enginedepth
        self.enginemaxmoves = enginemaxmoves
        self.boardstyle = boardstyle
        self.boardedges = boardedges

        self.executorgraph = [
            concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)
            for i in range(0, depth + 1)
        ]
        self.executorwork = concurrent.futures.ThreadPoolExecutor(
            max_workers=concurrency
        )
        self.visited = set()
        self.session = requests.Session()
        self.graph = graphviz.Digraph("ChessGraph", format="svg")
        self.cache = {}

        # We fix lichessbeta by giving the startpos a score of 0.35
        if self.source == "lichess":
            w, d, l, moves = self.lichess_api_call(
                "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"
            )
            self.lichessbeta = (1 - 0.35) / math.log((w + d + l) / w - 1)
        else:
            self.lichessbeta = None

    def load_cache(self):

        try:
            with open("chessgraph.cache.pyc", "rb") as f:
                self.cache = pickle.load(f)
        except:
            self.cache = {}

    def store_cache(self):

        with open("chessgraph.cache.pyc", "wb") as f:
            pickle.dump(self.cache, f)

    def get_moves(self, epd):

        if self.source == "chessdb":
            return self.get_moves_chessdb(epd)
        elif self.source == "engine":
            return self.get_moves_engine(epd)
        elif self.source == "lichess":
            return self.get_moves_lichess(epd)
        else:
            assert False

    def get_moves_engine(self, epd):

        key = (epd, self.engine, self.enginedepth, self.enginemaxmoves)

        if key in self.cache:
            return self.cache[key]

        moves = []
        engine = chess.engine.SimpleEngine.popen_uci(self.engine)
        board = chess.Board(epd)
        info = engine.analyse(
            board,
            chess.engine.Limit(depth=self.enginedepth),
            multipv=self.enginemaxmoves,
            info=chess.engine.INFO_SCORE | chess.engine.INFO_PV,
        )
        engine.quit()
        for i in info:
            moves.append(
                {
                    "score": i["score"].pov(board.turn).score(mate_score=30000),
                    "uci": chess.Move.uci(i["pv"][0]),
                }
            )

        self.cache[key] = moves

        return moves

    def get_moves_chessdb(self, epd):

        key = (epd, "chessdb")

        if key in self.cache:
            stdmoves = self.cache[key]
            if len(stdmoves) > 0:
                return stdmoves

        api = "http://www.chessdb.cn/cdb.php"
        url = api + "?action=queryall&board=" + parse.quote(epd) + "&json=1"
        timeout = 3

        moves = []
        try:
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            if data["status"] == "ok":
                moves = data["moves"]
            elif data["status"] == "unknown":
                pass
            elif data["status"] == "rate limited exceeded":
                sys.stderr.write("rate")
            else:
                sys.stderr.write(data)
        except:
            pass

        stdmoves = []
        for m in moves:
            stdmoves.append({"score": m["score"], "uci": m["uci"]})

        self.cache[key] = stdmoves

        return stdmoves

    def lichess_wdl_to_score(self, w, d, l):
        total = w + d + l

        if w == l:
            return 0.0

        if w == total:
            return 10000

        if l == total:
            return -10000

        if w > l:
            return min(
                10000, int(100 - 100 * self.lichessbeta * math.log(total / w - 1))
            )
        else:
            return max(
                -10000, -int(100 - 100 * self.lichessbeta * math.log(total / l - 1))
            )

    def lichess_api_call(self, epd):

        if self.lichessdb == "masters":
            specifics = "&topGames=0"
        else:
            specifics = (
                "variant=standard"
                + "&speeds=blitz"
                + "&ratings=2000,2200,2500"
                + "&topGames=0&recentGames=0"
            )

        url = (
            "https://explorer.lichess.ovh/{}?".format(self.lichessdb)
            + specifics
            + "&moves={}".format(self.enginemaxmoves)
            + "&fen={}".format(parse.quote(epd))
        )

        timeout = 3

        try:
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            data = response.json()

            if epd.split()[1] == "w":
                w, d, l = int(data["white"]), int(data["draws"]), int(data["black"])
            else:
                l, d, w = int(data["white"]), int(data["draws"]), int(data["black"])
            moves = data["moves"]
        except:
            w = d = l = 0
            moves = []

        return (w, d, l, moves)

    def get_moves_lichess(self, epd):

        key = (epd, "lichess", self.enginemaxmoves, self.lichessdb)

        if key in self.cache:
            stdmoves = self.cache[key]
            if len(stdmoves) > 0:
                return stdmoves

        w, d, l, moves = self.lichess_api_call(epd)

        stdmoves = []
        for m in moves:
            if epd.split()[1] == "w":
                w, d, l = int(m["white"]), int(m["draws"]), int(m["black"])
            else:
                l, d, w = int(m["white"]), int(m["draws"]), int(m["black"])
            total = w + d + l
            # A parameter that ensures we have sufficient games to get a score
            lichessmingames = 10
            if total > lichessmingames:
                score = self.lichess_wdl_to_score(w, d, l)
                stdmoves.append({"score": score, "uci": m["uci"]})

        self.cache[key] = stdmoves

        return stdmoves

    def node_name(self, board):

        if self.networkstyle == "graph":
            name = "graph - " + board.epd()
        elif self.networkstyle == "tree":
            movelist = []
            while True:
                try:
                    move = board.pop()
                    movelist.append(move)
                except:
                    break
            name = board.epd() + " moves "
            for move in reversed(movelist):
                board.push(move)
                name = name + " " + move.uci()
        else:
            raise ()

        return name

    def write_node(self, board, score, showboard, pvNode, tooltip):

        epd = board.epd()
        nodename = self.node_name(board)

        color = "gold" if board.turn == chess.WHITE else "burlywood4"
        penwidth = "3" if pvNode else "1"

        epdweb = parse.quote(epd)
        URL = "https://www.chessdb.cn/queryc_en/?" + epdweb
        image = None

        if showboard and not self.boardstyle == "none":
            if self.boardstyle == "unicode":
                label = board.unicode(empty_square="\u00B7")
            elif self.boardstyle == "svg":
                filename = (
                    "node-" + hashlib.sha256(epd.encode("utf-8")).hexdigest() + ".svg"
                )
                if not exists(filename):
                    cairosvg.svg2svg(
                        bytestring=chess.svg.board(board, size="200px").encode("utf-8"),
                        write_to=filename,
                    )
                image = filename
                label = ""
        else:
            label = (
                "None"
                if score is None
                else str(score if board.turn == chess.WHITE else -score)
            )

        if image:
            self.graph.node(
                nodename,
                label=label,
                shape="box",
                color=color,
                penwidth=penwidth,
                URL=URL,
                image=image,
                tooltip=tooltip,
            )
        else:
            self.graph.node(
                nodename,
                label=label,
                shape="box",
                color=color,
                penwidth=penwidth,
                fontname="Courier",
                URL=URL,
                tooltip=tooltip,
            )

    def write_edge(
        self, nodefrom, nodeto, sanmove, ucimove, turn, score, pvEdge, lateEdge
    ):

        color = "gold" if turn == chess.WHITE else "burlywood4"
        penwidth = "3" if pvEdge else "1"
        fontname = "Helvetica-bold" if pvEdge else "Helvectica"
        style = "dashed" if lateEdge else "solid"
        labeltooltip = "{} ({}) : {}".format(
            sanmove,
            ucimove,
            "None" if score is None else str(score if turn == chess.WHITE else -score),
        )
        tooltip = labeltooltip
        self.graph.edge(
            nodefrom,
            nodeto,
            label=sanmove,
            color=color,
            penwidth=penwidth,
            fontname=fontname,
            tooltip=tooltip,
            edgetooltip=tooltip,
            labeltooltip=labeltooltip,
            style=style,
        )

    def recurse(self, board, depth, alpha, beta, pvNode, plyFromRoot):

        nodenamefrom = self.node_name(board)
        legalMovesCount = board.legal_moves.count()
        epd = board.epd()

        # terminate recursion if visited
        if nodenamefrom in self.visited:
            return
        else:
            self.visited.add(nodenamefrom)

        if board.is_checkmate():
            moves = []
            bestscore = -30000
        elif (
            board.is_stalemate()
            or board.is_insufficient_material()
            or board.can_claim_draw()
        ):
            moves = []
            bestscore = 0
        else:
            moves = self.executorwork.submit(self.get_moves, epd).result()
            bestscore = None

        edgesfound = 0
        edgesdrawn = 0
        futures = []
        turn = board.turn
        tooltip = epd + "&#010;"

        # loop through the moves that are within delta of the bestmove
        for m in sorted(moves, key=lambda item: item["score"], reverse=True):

            score = int(m["score"])

            if bestscore is None:
                bestscore = score

            if score <= alpha:
                break

            ucimove = m["uci"]
            move = chess.Move.from_uci(ucimove)
            sanmove = board.san(move)
            board.push(move)
            nodenameto = self.node_name(board)
            edgesfound += 1
            pvEdge = pvNode and score == bestscore
            lateEdge = score != bestscore

            # no loops, otherwise recurse
            if score == bestscore:
                newDepth = depth - 1
            else:
                newDepth = depth - int(1.5 + math.log(edgesfound) / math.log(2))

            if newDepth >= 0:
                if nodenameto not in self.visited:
                    futures.append(
                        self.executorgraph[depth].submit(
                            self.recurse,
                            copy.deepcopy(board),
                            newDepth,
                            -beta,
                            -alpha,
                            pvEdge,
                            plyFromRoot + 1,
                        )
                    )
                edgesdrawn += 1
                tooltip += "{} : {}&#010;".format(
                    sanmove, str(score if turn == chess.WHITE else -score)
                )
                self.write_edge(
                    nodenamefrom,
                    nodenameto,
                    sanmove,
                    ucimove,
                    turn,
                    score,
                    pvEdge,
                    lateEdge,
                )

            board.pop()

        concurrent.futures.wait(futures)

        remainingMoves = legalMovesCount - edgesdrawn
        tooltip += "{} remaining {}&#010;".format(
            remainingMoves, "move" if remainingMoves == 1 else "moves"
        )

        if edgesdrawn == 0:
            tooltip += "terminal: {}".format(
                "None"
                if bestscore is None
                else str(bestscore if turn == chess.WHITE else -bestscore)
            )

        self.write_node(
            board,
            bestscore,
            edgesdrawn >= self.boardedges
            or (pvNode and edgesdrawn == 0)
            or plyFromRoot == 0,
            pvNode,
            tooltip,
        )

    def generate_graph(self, epd, alpha, beta):

        # set initial board
        board = chess.Board(epd)

        if board.turn == chess.WHITE:
            initialAlpha, initialBeta = alpha, beta
        else:
            initialAlpha, initialBeta = -beta, -alpha

        self.recurse(
            board, self.depth, initialAlpha, initialBeta, pvNode=True, plyFromRoot=0
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="An utility to create a graph of moves from a specified chess position. ",
    )

    parser.add_argument(
        "--networkstyle",
        choices=["graph", "tree"],
        type=str,
        default="graph",
        help="Selects the representation of the network as a graph (shows transpositions, compact) or a tree (simpler to follow, extended).",
    )

    parser.add_argument(
        "--depth",
        type=int,
        default=6,
        help="Maximum depth (in plies) of a followed variation",
    )

    parser.add_argument(
        "--alpha",
        type=int,
        default=0,
        help="Lower bound on the score of variations to be followed (for white)",
    )

    parser.add_argument(
        "--beta",
        type=int,
        default=15,
        help="Lower bound on the score of variations to be followed (for black)",
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=multiprocessing.cpu_count(),
        help="Number of cores to use for work / requests.",
    )

    parser.add_argument(
        "--position",
        type=str,
        default="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        help="FEN of the starting position.",
    )

    parser.add_argument(
        "--source",
        choices=["chessdb", "engine", "lichess"],
        type=str,
        default="chessdb",
        help="Use chessdb, lichess or an engine to score and rank moves",
    )

    parser.add_argument(
        "--lichessdb",
        choices=["masters", "lichess"],
        type=str,
        default="masters",
        help="Which lichess database to access, masters, or lichess players",
    )

    parser.add_argument(
        "--boardstyle",
        choices=["unicode", "svg", "none"],
        type=str,
        default="unicode",
        help="Which style to use to visualize a board.",
    )

    parser.add_argument(
        "--boardedges",
        type=int,
        default=3,
        help="Minimum number of edges needed before a board is visualized in the node.",
    )

    parser.add_argument(
        "--engine",
        type=str,
        default="stockfish.exe"
        if "windows" in platform.system().lower()
        else "stockfish",
        help="Name of the engine binary (with path as needed).",
    )

    parser.add_argument(
        "--enginedepth",
        type=int,
        default=20,
        help="Depth of the search used by the engine in evaluation",
    )

    parser.add_argument(
        "--enginemaxmoves",
        type=int,
        default=10,
        help="Maximum number of moves (MultiPV) considered by the engine in evaluation",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="chess.svg",
        help="Name of the output file (image in .svg format).",
    )

    parser.add_argument(
        "--embed",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If the individual svg boards should be embedded in the final .svg image. Unfortunately URLs are not preserved.",
    )

    parser.add_argument(
        "--purgecache",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Do no use, and later overwrite, the cache file stored on disk (chessgraph.cache.pyc).",
    )

    args = parser.parse_args()

    chessgraph = ChessGraph(
        networkstyle=args.networkstyle,
        depth=args.depth,
        concurrency=args.concurrency,
        source=args.source,
        lichessdb=args.lichessdb,
        engine=args.engine,
        enginedepth=args.enginedepth,
        enginemaxmoves=args.enginemaxmoves,
        boardstyle=args.boardstyle,
        boardedges=args.boardedges,
    )

    # load previously computed nodes in a cache
    if not args.purgecache:
        chessgraph.load_cache()

    # generate the content of the dotfile
    chessgraph.generate_graph(args.position, args.alpha, args.beta)

    # store updated cache
    chessgraph.store_cache()

    # generate the svg image (calls graphviz under the hood)
    svgpiped = chessgraph.graph.pipe()

    if args.embed:
        # this embeds the images of the boards generated.
        # Unfortunately, does remove the URLs that link to chessdb.
        # probably some smarter manipulation directly on the xml
        # would also allow to shrink the image size (each board embeds pieces etc.)
        cairosvg.svg2svg(
            bytestring=svgpiped,
            write_to=args.output,
        )
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(svgpiped.decode("utf-8"))
