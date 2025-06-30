"""Airspeed Velocity benchmarks for Dulwich core operations."""

import os
import random
import shutil
import string
import tempfile
import threading
import time

from dulwich import porcelain

# ASV's skip exception for benchmarks that can't run
try:
    from asv_runner.benchmarks.mark import SkipNotImplemented
except ImportError:
    # Fallback for older ASV versions
    SkipNotImplemented = NotImplementedError
from dulwich.client import (
    HttpGitClient,
    LocalGitClient,
)
from dulwich.diff_tree import tree_changes
from dulwich.objects import Blob, Commit, Tree
from dulwich.pack import Pack, PackData, PackIndex, write_pack_objects
from dulwich.repo import Repo
from dulwich.walk import Walker

# These modules might not exist in older versions
try:
    from dulwich.server import FileSystemBackend
except ImportError:
    FileSystemBackend = None

try:
    from dulwich.web import (
        GunzipFilter,
        HTTPGitApplication,
        make_server,
    )
except ImportError:
    GunzipFilter = HTTPGitApplication = make_server = None


class BenchmarkBase:
    """Base class for benchmarks with common setup/teardown."""

    def setup(self):
        """Create temporary directory for benchmarks."""
        self.tmpdir = tempfile.mkdtemp()
        self.repo_path = os.path.join(self.tmpdir, "repo")

    def teardown(self, *args):
        """Clean up temporary directory."""
        if hasattr(self, "tmpdir") and os.path.exists(self.tmpdir):
            shutil.rmtree(self.tmpdir)


class LargeHistoryBenchmarks(BenchmarkBase):
    """Benchmarks for operations on repositories with large histories."""

    # Reduced parameters for testing compatibility across versions
    params = ([100, 500], [10, 50])
    param_names = ["num_commits", "files_per_commit"]

    def setup(self, num_commits, files_per_commit):
        """Create repository with large history."""
        super().setup()
        os.makedirs(self.repo_path, exist_ok=True)
        self.repo = Repo.init(self.repo_path)
        self.num_commits = num_commits
        self.files_per_commit = files_per_commit

        # Generate large history
        parent = None
        self.commits = []

        for i in range(num_commits):
            # Modify random files
            for j in range(files_per_commit):
                file_idx = random.randint(0, files_per_commit * 10)
                path = os.path.join(self.repo_path, f"file{file_idx}.txt")
                with open(path, "w") as f:
                    # Write random content to simulate real changes
                    content = "".join(
                        random.choices(string.ascii_letters + string.digits, k=1000)
                    )
                    f.write(f"Commit {i} modification {j}\n{content}\n")

            # Stage all changes (handle API compatibility)
            try:
                # Get all file*.txt files
                files_to_stage = [f"file{j}.txt" for j in range(files_per_commit)]
                self.repo.stage(files_to_stage)
            except AttributeError:
                # Older versions don't have stage method
                # Add files to index manually
                from dulwich.index import index_entry_from_stat

                index = self.repo.open_index()
                for j in range(files_per_commit):
                    filename = f"file{j}.txt"
                    file_path = os.path.join(self.repo_path, filename)
                    st = os.lstat(file_path)
                    blob = Blob.from_string(
                        f"Content for file {j} in commit {i}\n".encode()
                    )
                    self.repo.object_store.add_object(blob)
                    index[filename.encode()] = index_entry_from_stat(st, blob.id, 0)
                index.write()

            # Create commit (handle API compatibility)
            try:
                # Try new API first (parent_commits)
                commit_id = self.repo.do_commit(
                    f"Commit {i}".encode(),
                    committer=b"Test User <test@example.com>",
                    author=b"Test User <test@example.com>",
                    parent_commits=[parent] if parent else [],
                )
            except TypeError:
                # Fall back to old API (no parent parameter - uses HEAD)
                if parent and i > 0:
                    # Set HEAD to parent before committing
                    self.repo.refs[b"HEAD"] = parent
                commit_id = self.repo.do_commit(
                    f"Commit {i}".encode(),
                    committer=b"Test User <test@example.com>",
                    author=b"Test User <test@example.com>",
                )
            self.commits.append(commit_id)
            parent = commit_id

            # Create branches at intervals
            if i % 100 == 0:
                self.repo.refs[f"refs/heads/branch-{i}".encode()] = commit_id

            # Create tags at intervals
            if i % 50 == 0:
                self.repo.refs[f"refs/tags/v{i}".encode()] = commit_id

    def time_walk_full_history(self, num_commits, files_per_commit):
        """Time walking through entire history."""
        walker = Walker(self.repo.object_store, [self.commits[-1]])
        count = 0
        for entry in walker:
            count += 1
        assert count == self.num_commits

    def time_walk_limited_history(self, num_commits, files_per_commit):
        """Time walking through limited history (last 100 commits)."""
        walker = Walker(self.repo.object_store, [self.commits[-1]], max_entries=100)
        list(walker)

    def time_log_with_paths(self, num_commits, files_per_commit):
        """Time log with path filtering."""
        walker = Walker(
            self.repo.object_store,
            [self.commits[-1]],
            paths=[b"file1.txt", b"file2.txt"],
        )
        list(walker)

    def time_rev_list(self, num_commits, files_per_commit):
        """Time rev-list equivalent operation."""
        # Get all commits reachable from HEAD
        walker = Walker(self.repo.object_store, [self.commits[-1]])
        commits = [entry.commit.id for entry in walker]

    def time_merge_base(self, num_commits, files_per_commit):
        """Time finding merge base between branches."""
        if num_commits >= 200:
            try:
                from dulwich.graph import find_merge_base
                
                # Find merge base between two branches
                branch1 = self.repo.refs[b"refs/heads/branch-0"]
                branch2 = self.repo.refs[
                    f"refs/heads/branch-{(num_commits // 100) * 100}".encode()
                ]
                find_merge_base(self.repo.object_store, [branch1, branch2])
            except ImportError:
                # Skip if graph module doesn't exist in older versions
                raise SkipNotImplemented("find_merge_base not available in this version")

    def time_log_with_patches(self, num_commits, files_per_commit):
        """Time verbose log with patches (git log -p equivalent)."""
        import io

        outf = io.StringIO()
        # Use porcelain.log with patches
        porcelain.log(self.repo.path, outstream=outf, max_entries=100)

    def time_show_commits(self, num_commits, files_per_commit):
        """Time showing commits with full diff (git show equivalent)."""
        import io

        # Show last 50 commits
        for commit_id in self.commits[-50:]:
            outf = io.StringIO()
            porcelain.show(self.repo.path, objectish=commit_id, outstream=outf)

    def time_diff_tree(self, num_commits, files_per_commit):
        """Time diff-tree operations."""
        # Diff between consecutive commits
        for i in range(min(50, len(self.commits) - 1)):
            porcelain.diff_tree(self.repo.path, self.commits[i], self.commits[i + 1])


class DiskObjectStoreBenchmarks(BenchmarkBase):
    """Benchmarks for disk-based object store operations."""

    params = ([1000, 10000, 50000], ["loose", "packed", "mixed"])
    param_names = ["num_objects", "storage_type"]

    def setup(self, num_objects, storage_type):
        """Create disk object store with objects in different storage formats."""
        super().setup()
        os.makedirs(self.repo_path, exist_ok=True)
        self.repo = Repo.init(self.repo_path)
        self.store = self.repo.object_store
        self.num_objects = num_objects
        self.object_ids = []

        # Create objects
        objects_data = []
        for i in range(num_objects):
            # Vary content size
            size = random.choice([100, 1000, 10000])
            content = "".join(random.choices(string.ascii_letters, k=size))
            blob = Blob.from_string(f"Object {i}\n{content}".encode())

            if storage_type == "loose" or storage_type == "mixed":
                self.store.add_object(blob)
            else:
                objects_data.append(blob)

            self.object_ids.append(blob.id)

        # Pack objects if needed
        if storage_type == "packed" or (storage_type == "mixed" and objects_data):
            pack_dir = os.path.join(self.repo_path, ".git/objects/pack")
            os.makedirs(pack_dir, exist_ok=True)
            pack_path = os.path.join(pack_dir, "pack-benchmark.pack")

            # For packed, use all objects; for mixed, use half
            if storage_type == "mixed":
                objects_to_pack = objects_data[: len(objects_data) // 2]
            else:
                objects_to_pack = objects_data

            with open(pack_path, "wb") as f:
                write_pack_objects(f.write, objects_to_pack)

            # Create index
            pack_data = PackData(pack_path)
            pack_data.create_index_v2(pack_path.replace(".pack", ".idx"))

            # Re-open repository to recognize new pack
            self.repo = Repo(self.repo_path)
            self.store = self.repo.object_store

    def time_read_objects(self, num_objects, storage_type):
        """Time reading objects from disk."""
        sample_size = min(100, num_objects // 10)
        for i in range(sample_size):
            idx = random.randint(0, num_objects - 1)
            self.store[self.object_ids[idx]]

    def time_contains_check(self, num_objects, storage_type):
        """Time checking object existence."""
        sample_size = min(200, num_objects // 5)
        for i in range(sample_size):
            idx = random.randint(0, num_objects - 1)
            self.object_ids[idx] in self.store

    def time_iter_shas(self, num_objects, storage_type):
        """Time iterating through all object SHAs."""
        count = 0
        for sha in self.store:
            count += 1


class PackFileDiskBenchmarks(BenchmarkBase):
    """Benchmarks for pack file operations on disk."""

    params = ([1000, 10000, 50000], [False, True])
    param_names = ["num_objects", "with_deltas"]

    def setup(self, num_objects, with_deltas):
        """Create pack files on disk."""
        super().setup()
        self.num_objects = num_objects
        self.with_deltas = with_deltas

        # Create objects for the pack
        self.objects = []
        base_content = "".join(random.choices(string.ascii_letters, k=10000))

        for i in range(num_objects):
            if with_deltas and i > 0 and i % 10 != 0:
                # Create similar content for delta compression
                content = (
                    base_content[:9000] + f"\nModification {i}\n" + base_content[9000:]
                )
            else:
                # Create unique content
                content = "".join(
                    random.choices(string.ascii_letters + string.digits, k=10000)
                )
                if with_deltas:
                    base_content = content

            blob = Blob.from_string(content.encode() if isinstance(content, str) else content)
            self.objects.append(blob)

        # Write pack file
        self.pack_path = os.path.join(self.tmpdir, "test.pack")
        with open(self.pack_path, "wb") as f:
            write_pack_objects(f.write, self.objects)

        # Create index
        self.pack_data = PackData(self.pack_path)
        self.pack_index = self.pack_data.create_index_v2(
            os.path.join(self.tmpdir, "test.idx")
        )
        self.pack = Pack(os.path.join(self.tmpdir, "test"))

    def time_pack_random_access(self, num_objects, with_deltas):
        """Time random access to pack objects."""
        # Access random objects
        for _ in range(100):
            idx = random.randint(0, num_objects - 1)
            sha = self.objects[idx].id
            self.pack[sha]

    def time_pack_sequential_read(self, num_objects, with_deltas):
        """Time sequential reading of pack objects."""
        # Read first 100 objects sequentially
        for i in range(min(100, num_objects)):
            sha = self.objects[i].id
            self.pack[sha]

    def time_pack_index_load(self, num_objects, with_deltas):
        """Time loading pack index from disk."""
        # Force reload of index
        idx_path = os.path.join(self.tmpdir, "test.idx")
        PackIndex(idx_path)

    def time_verify_pack(self, num_objects, with_deltas):
        """Time verifying pack integrity."""
        self.pack_data.check()


class ClientServerBenchmarks(BenchmarkBase):
    """Benchmarks for client/server protocol operations."""

    params = ([100, 1000], ["fetch", "push", "clone"])
    param_names = ["num_commits", "operation"]

    def setup(self, num_commits, operation):
        """Setup client and server repositories."""
        super().setup()

        # Create server repository
        self.server_path = os.path.join(self.tmpdir, "server")
        os.makedirs(self.server_path, exist_ok=True)
        self.server_repo = Repo.init_bare(self.server_path)

        # Populate server repository
        temp_path = os.path.join(self.tmpdir, "temp")
        os.makedirs(temp_path, exist_ok=True)
        temp_repo = Repo.init(temp_path)

        for i in range(num_commits):
            filename = f"file{i}.txt"
            path = os.path.join(temp_path, filename)
            with open(path, "w") as f:
                f.write(f"Server content {i}\n" * 100)
            temp_repo.stage([filename])
            temp_repo.do_commit(f"Server commit {i}".encode())

        # Push to server
        porcelain.push(temp_repo, self.server_path, "master")
        shutil.rmtree(temp_path)

        # Create client repository for fetch/push
        if operation != "clone":
            self.client_path = os.path.join(self.tmpdir, "client")
            porcelain.clone(self.server_path, self.client_path)
            self.client_repo = Repo(self.client_path)

    def time_local_clone(self, num_commits, operation):
        """Time cloning over local protocol."""
        if operation == "clone":
            clone_path = os.path.join(self.tmpdir, "clone_test")
            porcelain.clone(self.server_path, clone_path)

    def time_local_fetch(self, num_commits, operation):
        """Time fetching over local protocol."""
        if operation == "fetch":
            # Add new commits to server
            temp_path = os.path.join(self.tmpdir, "temp2")
            os.makedirs(temp_path, exist_ok=True)
            temp_repo = Repo.init(temp_path)

            # Clone first to get existing content
            porcelain.clone(self.server_path, temp_path)

            # Add new commits
            for i in range(10):
                filename = f"new_file{i}.txt"
                path = os.path.join(temp_path, filename)
                with open(path, "w") as f:
                    f.write(f"New content {i}\n")
                temp_repo.stage([filename])
                temp_repo.do_commit(f"New commit {i}".encode())

            # Push to server
            porcelain.push(temp_repo, self.server_path, "master")
            shutil.rmtree(temp_path)

            # Fetch from client
            porcelain.fetch(self.client_repo, self.server_path)

    def time_local_push(self, num_commits, operation):
        """Time pushing over local protocol."""
        if operation == "push":
            # Add commits to client
            for i in range(10):
                filename = f"client_file{i}.txt"
                path = os.path.join(self.client_path, filename)
                with open(path, "w") as f:
                    f.write(f"Client content {i}\n")
                self.client_repo.stage([filename])
                self.client_repo.do_commit(f"Client commit {i}".encode())

            # Push to server
            porcelain.push(self.client_repo, self.server_path, "master")


class HTTPProtocolBenchmarks(BenchmarkBase):
    """Benchmarks for HTTP smart protocol operations."""

    params = ([100, 1000], [True, False])
    param_names = ["num_commits", "use_compression"]

    def setup(self, num_commits, use_compression):
        """Setup HTTP server and repositories."""
        super().setup()
        
        # Skip if web modules aren't available
        if FileSystemBackend is None or HTTPGitApplication is None or make_server is None:
            raise SkipNotImplemented("HTTP server modules not available in this version")

        # Create server repository
        self.server_path = os.path.join(self.tmpdir, "server")
        os.makedirs(self.server_path, exist_ok=True)
        self.server_repo = Repo.init_bare(self.server_path)

        # Populate server
        temp_path = os.path.join(self.tmpdir, "temp")
        os.makedirs(temp_path, exist_ok=True)
        temp_repo = Repo.init(temp_path)

        for i in range(num_commits):
            filename = f"file{i}.txt"
            path = os.path.join(temp_path, filename)
            with open(path, "w") as f:
                f.write(f"HTTP content {i}\n" * 100)
            temp_repo.stage([filename])
            temp_repo.do_commit(f"HTTP commit {i}".encode())

        porcelain.push(temp_repo, self.server_path, "master")
        shutil.rmtree(temp_path)

        # Setup HTTP server
        backend = FileSystemBackend(self.server_path)
        app = HTTPGitApplication(backend)

        if use_compression:
            app = GunzipFilter(app)

        self.server = make_server("localhost", 0, app)
        self.port = self.server.server_port
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

        # Give server time to start
        time.sleep(0.1)

    def teardown(self, *args):
        """Shutdown HTTP server and cleanup."""
        if hasattr(self, "server"):
            self.server.shutdown()
            self.server_thread.join()
        super().teardown(*args)

    def time_http_clone(self, num_commits, use_compression):
        """Time cloning over HTTP."""
        clone_path = os.path.join(self.tmpdir, "http_clone")
        url = f"http://localhost:{self.port}/"
        porcelain.clone(url, clone_path)

    def time_http_fetch_pack(self, num_commits, use_compression):
        """Time fetch-pack over HTTP."""
        url = f"http://localhost:{self.port}/"
        client = HttpGitClient(url)

        def determine_wants(refs):
            return [sha for ref, sha in refs.items() if ref != b"HEAD"]

        client.fetch_pack(
            "/", determine_wants, lambda data: None, progress=lambda msg: None
        )


class PackNegotiationBenchmarks(BenchmarkBase):
    """Benchmarks for pack negotiation algorithms."""

    params = ([100, 1000, 5000], [0, 50, 90])
    param_names = ["num_commits", "common_history_percent"]

    def setup(self, num_commits, common_history_percent):
        """Setup repositories with varying amounts of common history."""
        super().setup()

        # Create server repository
        self.server_path = os.path.join(self.tmpdir, "server")
        os.makedirs(self.server_path, exist_ok=True)
        self.server_repo = Repo.init_bare(self.server_path)

        # Create temp repo for commits
        temp_path = os.path.join(self.tmpdir, "temp")
        os.makedirs(temp_path, exist_ok=True)
        temp_repo = Repo.init(temp_path)

        # Create common commits
        common_commits = (num_commits * common_history_percent) // 100
        self.common_shas = []

        for i in range(common_commits):
            filename = f"common{i}.txt"
            path = os.path.join(temp_path, filename)
            with open(path, "w") as f:
                f.write(f"Common content {i}\n" * 50)
            temp_repo.stage([filename])
            sha = temp_repo.do_commit(f"Common commit {i}".encode())
            self.common_shas.append(sha)

        # Push common history to server
        porcelain.push(temp_repo, self.server_path, "master")

        # Create client with common history
        self.client_path = os.path.join(self.tmpdir, "client")
        porcelain.clone(self.server_path, self.client_path)
        self.client_repo = Repo(self.client_path)

        # Add divergent commits to server
        for i in range(common_commits, num_commits):
            filename = f"server{i}.txt"
            path = os.path.join(temp_path, filename)
            with open(path, "w") as f:
                f.write(f"Server only content {i}\n" * 50)
            temp_repo.stage([filename])
            temp_repo.do_commit(f"Server only commit {i}".encode())

        # Push server-only commits
        porcelain.push(temp_repo, self.server_path, "master")
        shutil.rmtree(temp_path)

    def time_negotiate_pack(self, num_commits, common_history_percent):
        """Time pack negotiation process."""
        client = LocalGitClient()
        server_refs = self.server_repo.get_refs()

        def determine_wants(refs):
            # Want everything we don't have
            return [
                sha
                for ref, sha in refs.items()
                if ref != b"HEAD" and sha not in self.client_repo.object_store
            ]

        def generate_pack_data(have, want, ofs_delta=False):
            # Simulate pack generation
            objects = []
            for sha in want:
                obj = self.server_repo.object_store[sha]
                objects.append((obj.type_name, obj.as_raw_string()))
            return objects

        # Simulate negotiation
        wants = determine_wants(server_refs)
        haves = [
            sha for sha in self.common_shas if sha in self.client_repo.object_store
        ]

        if wants:
            pack_data = generate_pack_data(haves, wants)


class LargeFileBenchmarks(BenchmarkBase):
    """Benchmarks for handling large files."""

    params = [1, 10, 50, 100]  # MB
    param_names = ["file_size_mb"]

    def setup(self, file_size_mb):
        """Create repository with large files."""
        super().setup()
        os.makedirs(self.repo_path, exist_ok=True)
        self.repo = Repo.init(self.repo_path)
        self.file_size_mb = file_size_mb

        # Create large file
        self.large_file_name = "large_file.bin"
        self.large_file = os.path.join(self.repo_path, self.large_file_name)
        content = os.urandom(file_size_mb * 1024 * 1024)
        with open(self.large_file, "wb") as f:
            f.write(content)

    def time_add_large_file(self, file_size_mb):
        """Time adding large file to repository."""
        self.repo.stage([self.large_file_name])
        self.repo.do_commit(b"Add large file")

    def time_diff_large_file(self, file_size_mb):
        """Time diffing large file changes."""
        # First commit
        self.repo.stage([self.large_file_name])
        commit1 = self.repo.do_commit(b"Initial large file")

        # Modify file
        with open(self.large_file, "ab") as f:
            f.write(b"Additional content\n")

        self.repo.stage([self.large_file_name])
        commit2 = self.repo.do_commit(b"Modified large file")

        # Diff the commits
        tree1 = self.repo[commit1].tree
        tree2 = self.repo[commit2].tree
        list(tree_changes(self.repo.object_store, tree1, tree2))


class BranchOperationBenchmarks(BenchmarkBase):
    """Benchmarks for branch operations."""

    params = [10, 100, 1000]
    param_names = ["num_branches"]

    def setup(self, num_branches):
        """Create repository with many branches."""
        super().setup()
        os.makedirs(self.repo_path, exist_ok=True)
        self.repo = Repo.init(self.repo_path)
        self.num_branches = num_branches

        # Create initial commit
        path = os.path.join(self.repo_path, "initial.txt")
        with open(path, "w") as f:
            f.write("Initial content\n")
        self.repo.stage(["initial.txt"])
        base_commit = self.repo.do_commit(b"Initial commit")

        # Create branches with different commits
        self.branch_commits = {}
        for i in range(num_branches):
            # Create unique commit for each branch
            filename = f"branch{i}.txt"
            path = os.path.join(self.repo_path, filename)
            with open(path, "w") as f:
                f.write(f"Branch {i} content\n")
            self.repo.stage([filename])

            # Handle API compatibility
            try:
                commit = self.repo.do_commit(
                    f"Branch {i} commit".encode(), parent_commits=[base_commit]
                )
            except TypeError:
                # Fall back to old API - set HEAD to base commit before committing
                self.repo.refs[b"HEAD"] = base_commit
                commit = self.repo.do_commit(f"Branch {i} commit".encode())

            branch_name = f"refs/heads/branch-{i}".encode()
            self.repo.refs[branch_name] = commit
            self.branch_commits[branch_name] = commit

    def time_list_branches(self, num_branches):
        """Time listing all branches."""
        refs = self.repo.get_refs()
        branches = [ref for ref in refs if ref.startswith(b"refs/heads/")]

    def time_switch_branch(self, num_branches):
        """Time switching between branches."""
        for i in range(min(10, num_branches)):
            branch = f"refs/heads/branch-{i}".encode()
            self.repo.refs.set_symbolic_ref(b"HEAD", branch)

    def time_merge_branches(self, num_branches):
        """Time merging branches."""
        if num_branches >= 2:
            # Simple merge simulation
            branch1_commit = self.branch_commits[b"refs/heads/branch-0"]
            branch2_commit = self.branch_commits[b"refs/heads/branch-1"]

            # Create merge commit
            merge_commit = Commit()
            merge_commit.tree = self.repo[branch1_commit].tree
            merge_commit.parents = [branch1_commit, branch2_commit]
            merge_commit.author = merge_commit.committer = (
                b"Test User <test@example.com>"
            )
            merge_commit.commit_time = merge_commit.author_time = 1234567890
            merge_commit.commit_timezone = merge_commit.author_timezone = 0
            merge_commit.message = b"Merge branches"

            self.repo.object_store.add_object(merge_commit)


class StatusBenchmarks(BenchmarkBase):
    """Benchmarks for status operations."""

    params = ([100, 1000, 5000], [10, 50, 100])
    param_names = ["num_files", "percent_modified"]

    def setup(self, num_files, percent_modified):
        """Create repository with many files in various states."""
        super().setup()
        os.makedirs(self.repo_path, exist_ok=True)
        self.repo = Repo.init(self.repo_path)
        self.num_files = num_files

        # Create initial files and commit
        for i in range(num_files):
            path = os.path.join(self.repo_path, f"dir{i % 10}/file{i}.txt")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(f"Initial content {i}\n")

        self.repo.stage([f"dir{i % 10}/file{i}.txt" for i in range(num_files)])
        self.repo.do_commit(b"Initial commit")

        # Modify some files
        num_modified = (num_files * percent_modified) // 100
        for i in range(num_modified):
            path = os.path.join(self.repo_path, f"dir{i % 10}/file{i}.txt")
            with open(path, "a") as f:
                f.write(f"Modified content {i}\n")

        # Stage some of the modified files
        num_staged = num_modified // 2
        self.repo.stage([f"dir{i % 10}/file{i}.txt" for i in range(num_staged)])

        # Add some new untracked files
        for i in range(num_files, num_files + 50):
            path = os.path.join(self.repo_path, f"untracked{i}.txt")
            with open(path, "w") as f:
                f.write(f"Untracked file {i}\n")

    def time_status(self, num_files, percent_modified):
        """Time getting repository status."""
        porcelain.status(self.repo.path)

    def time_diff_index(self, num_files, percent_modified):
        """Time diffing against index."""
        try:
            from dulwich.index import get_unstaged_changes
            list(get_unstaged_changes(self.repo.open_index(), self.repo.path))
        except (ImportError, AttributeError):
            raise SkipNotImplemented("get_unstaged_changes not available in this version")


class GarbageCollectionBenchmarks(BenchmarkBase):
    """Benchmarks for garbage collection operations."""

    params = ([100, 1000, 5000], [0, 10, 50])
    param_names = ["num_loose_objects", "unreachable_percent"]

    def setup(self, num_loose_objects, unreachable_percent):
        """Create repository with many loose objects and some unreachable."""
        super().setup()
        os.makedirs(self.repo_path, exist_ok=True)
        self.repo = Repo.init(self.repo_path)

        # Create reachable objects in commits
        num_reachable = num_loose_objects * (100 - unreachable_percent) // 100
        parent = None
        for i in range(0, num_reachable, 10):
            # Create 10 blobs per commit
            tree = Tree()
            for j in range(min(10, num_reachable - i)):
                blob = Blob.from_string((f"Reachable object {i + j}\n" * 100).encode())
                self.repo.object_store.add_object(blob)
                tree.add(f"file{j}.txt".encode(), 0o100644, blob.id)
            self.repo.object_store.add_object(tree)

            commit = Commit()
            commit.tree = tree.id
            commit.author = commit.committer = b"Test User <test@example.com>"
            commit.commit_time = commit.author_time = 1234567890 + i
            commit.commit_timezone = commit.author_timezone = 0
            commit.message = f"Commit {i // 10}".encode()
            if parent:
                commit.parents = [parent]
            self.repo.object_store.add_object(commit)
            parent = commit.id

        if parent:
            self.repo.refs[b"refs/heads/master"] = parent

        # Create unreachable loose objects
        num_unreachable = num_loose_objects * unreachable_percent // 100
        for i in range(num_unreachable):
            blob = Blob.from_string((f"Unreachable object {i}\n" * 100).encode())
            self.repo.object_store.add_object(blob)

        # Create some existing pack files
        objects = []
        for i in range(100):
            blob = Blob.from_string((f"Already packed object {i}\n" * 100).encode())
            objects.append(blob)

        pack_path = os.path.join(self.repo_path, ".git/objects/pack/pack-existing.pack")
        os.makedirs(os.path.dirname(pack_path), exist_ok=True)
        with open(pack_path, "wb") as f:
            write_pack_objects(f.write, objects)

        # Create index
        pack_data = PackData(pack_path)
        pack_data.create_index_v2(pack_path.replace(".pack", ".idx"))

    def time_count_objects(self, num_loose_objects, unreachable_percent):
        """Time counting objects using porcelain.count_objects."""
        try:
            from dulwich.porcelain import count_objects
            count_objects(self.repo)
        except (ImportError, AttributeError):
            # Function might not exist in older versions
            raise SkipNotImplemented("Function not available in this version")

    def time_gc(self, num_loose_objects, unreachable_percent):
        """Time full garbage collection."""
        try:
            from dulwich.porcelain import gc
            gc(self.repo)
        except (ImportError, AttributeError):
            # Function might not exist in older versions
            raise SkipNotImplemented("Function not available in this version")

    def time_repack(self, num_loose_objects, unreachable_percent):
        """Time repacking repository."""
        try:
            from dulwich.porcelain import repack
            repack(self.repo)
        except (ImportError, AttributeError):
            # Function might not exist in older versions
            raise SkipNotImplemented("Function not available in this version")

    def time_prune(self, num_loose_objects, unreachable_percent):
        """Time pruning unreachable objects."""
        try:
            from dulwich.porcelain import prune
            prune(self.repo)
        except (ImportError, AttributeError):
            # Function might not exist in older versions
            raise SkipNotImplemented("Function not available in this version")

    def time_fsck(self, num_loose_objects, unreachable_percent):
        """Time filesystem consistency check."""
        try:
            from dulwich.porcelain import fsck
            fsck(self.repo)
        except (ImportError, AttributeError):
            # Function might not exist in older versions
            raise SkipNotImplemented("Function not available in this version")


class SymrefBenchmarks(BenchmarkBase):
    """Benchmarks for symbolic reference operations."""

    params = ([10, 100, 1000], [1, 2, 4])
    param_names = ["num_refs", "symref_depth"]

    def setup(self, num_refs, symref_depth):
        """Create repository with symbolic references."""
        super().setup()
        os.makedirs(self.repo_path, exist_ok=True)
        self.repo = Repo.init(self.repo_path)
        self.num_refs = num_refs
        self.symref_depth = symref_depth
        
        # Create base refs
        path = os.path.join(self.repo_path, "file.txt")
        with open(path, "w") as f:
            f.write("Test content\n")
        self.repo.stage(["file.txt"])
        commit_id = self.repo.do_commit(b"Initial commit")
        
        # Create regular refs that will be targets
        for i in range(num_refs):
            ref_name = f"refs/heads/branch-{i}".encode()
            self.repo.refs[ref_name] = commit_id
        
        # Create symref chains of varying depths
        for i in range(0, num_refs, 10):
            # Create chain: symref-0 -> symref-1 -> ... -> branch-i
            target = f"refs/heads/branch-{i}".encode()
            for j in range(symref_depth - 1, -1, -1):
                symref_name = f"refs/heads/symref-{i}-{j}".encode()
                self.repo.refs.set_symbolic_ref(symref_name, target)
                target = symref_name
        
        # Also create some remote refs with HEAD symrefs
        for i in range(0, min(10, num_refs)):
            remote_name = f"remote-{i}"
            # Create remote HEAD pointing to a branch
            remote_head = f"refs/remotes/{remote_name}/HEAD".encode()
            remote_branch = f"refs/remotes/{remote_name}/master".encode() 
            self.repo.refs[remote_branch] = commit_id
            self.repo.refs.set_symbolic_ref(remote_head, remote_branch)

    def time_read_symref(self, num_refs, symref_depth):
        """Time reading symbolic references."""
        for i in range(0, min(100, num_refs), 10):
            # Read the head of a symref chain
            symref_name = f"refs/heads/symref-{i}-0".encode()
            self.repo.refs[symref_name]
    
    def time_follow_symref(self, num_refs, symref_depth):
        """Time following symbolic reference chains."""
        for i in range(0, min(100, num_refs), 10):
            symref_name = f"refs/heads/symref-{i}-0".encode()
            self.repo.refs.follow(symref_name)
    
    def time_set_symref(self, num_refs, symref_depth):
        """Time setting symbolic references."""
        for i in range(min(50, num_refs)):
            new_symref = f"refs/heads/new-symref-{i}".encode()
            target = f"refs/heads/branch-{i}".encode()
            self.repo.refs.set_symbolic_ref(new_symref, target)
    
    def time_update_symref_target(self, num_refs, symref_depth):
        """Time updating targets of existing symbolic references."""
        for i in range(0, min(50, num_refs), 10):
            symref_name = f"refs/heads/symref-{i}-0".encode()
            new_target = f"refs/heads/branch-{(i + 1) % num_refs}".encode()
            self.repo.refs.set_symbolic_ref(symref_name, new_target)
    
    def time_list_refs_with_symrefs(self, num_refs, symref_depth):
        """Time listing all refs including symrefs."""
        refs = self.repo.get_refs()
        # Force iteration
        list(refs.items())
    
    def time_read_remote_head(self, num_refs, symref_depth):
        """Time reading remote HEAD symrefs."""
        for i in range(min(10, num_refs)):
            remote_head = f"refs/remotes/remote-{i}/HEAD".encode()
            try:
                self.repo.refs[remote_head]
            except KeyError:
                raise SkipNotImplemented("Function not available in this version")
    
    def time_resolve_remote_symrefs(self, num_refs, symref_depth):
        """Time resolving remote symrefs to their targets."""
        for i in range(min(10, num_refs)):
            remote_head = f"refs/remotes/remote-{i}/HEAD".encode()
            try:
                self.repo.refs.follow(remote_head)
            except KeyError:
                raise SkipNotImplemented("Function not available in this version")
            except AttributeError:
                raise SkipNotImplemented("refs.follow not available in this version")


class RepackingBenchmarks(BenchmarkBase):
    """Benchmarks for repository repacking operations."""

    params = ([10, 50, 100], [100, 1000, 5000], [False, True])
    param_names = ["num_packs", "objects_per_pack", "with_deltas"]

    def setup(self, num_packs, objects_per_pack, with_deltas):
        """Create repository with multiple pack files."""
        super().setup()
        os.makedirs(self.repo_path, exist_ok=True)
        self.repo = Repo.init(self.repo_path)

        # Create multiple pack files
        pack_dir = os.path.join(self.repo_path, ".git/objects/pack")
        os.makedirs(pack_dir, exist_ok=True)

        base_content = "".join(random.choices(string.ascii_letters, k=10000))

        for pack_idx in range(num_packs):
            objects = []

            for obj_idx in range(objects_per_pack):
                if with_deltas and obj_idx > 0 and obj_idx % 10 != 0:
                    # Create similar content for delta compression
                    content = (
                        base_content[:9000]
                        + f"\nPack {pack_idx} Object {obj_idx}\n"
                        + base_content[9000:]
                    )
                else:
                    # Create unique content
                    content = "".join(
                        random.choices(string.ascii_letters + string.digits, k=10000)
                    )
                    if with_deltas:
                        base_content = content

                blob = Blob.from_string(f"Pack {pack_idx} Object {obj_idx}\n{content}".encode())
                objects.append(blob)

                # Add some to a tree periodically
                if obj_idx % 20 == 0:
                    tree = Tree()
                    tree.add(f"file{obj_idx}.txt".encode(), 0o100644, blob.id)
                    objects.append(tree)

            # Write pack file
            pack_path = os.path.join(pack_dir, f"pack-{pack_idx:04d}.pack")
            with open(pack_path, "wb") as f:
                write_pack_objects(f.write, objects)

            # Create index
            pack_data = PackData(pack_path)
            pack_data.create_index_v2(pack_path.replace(".pack", ".idx"))

        # Create some loose objects too
        for i in range(100):
            blob = Blob.from_string((f"Loose object {i}\n" * 50).encode())
            self.repo.object_store.add_object(blob)

    def time_repack_all(self, num_packs, objects_per_pack, with_deltas):
        """Time repacking all objects into a single pack."""
        try:
            from dulwich.porcelain import repack
            repack(self.repo)
        except (ImportError, AttributeError):
            raise SkipNotImplemented("repack not available in this version")

    def time_repack_incremental(self, num_packs, objects_per_pack, with_deltas):
        """Time incremental repacking."""
        # This would need incremental repack support in dulwich
        # For now, use regular repack
        try:
            from dulwich.porcelain import repack
            repack(self.repo)
        except (ImportError, AttributeError):
            raise SkipNotImplemented("repack not available in this version")

    def time_pack_refs(self, num_packs, objects_per_pack, with_deltas):
        """Time packing references."""
        # Create many refs first
        for i in range(100):
            ref_name = f"refs/heads/branch-{i}".encode()
            # Point to a random object (simplified)
            self.repo.refs[ref_name] = b"0" * 40

        try:
            from dulwich.porcelain import pack_refs
            pack_refs(self.repo)
        except (ImportError, AttributeError):
            raise SkipNotImplemented("pack_refs not available in this version")

    def time_optimize_packs(self, num_packs, objects_per_pack, with_deltas):
        """Time optimizing pack files (reindex, verify, etc)."""
        # Verify all packs
        pack_dir = os.path.join(self.repo_path, ".git/objects/pack")
        for filename in os.listdir(pack_dir):
            if filename.endswith(".pack"):
                pack_path = os.path.join(pack_dir, filename)
                pack_data = PackData(pack_path)
                pack_data.check()
