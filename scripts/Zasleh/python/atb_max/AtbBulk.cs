using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using Autodesk.Max;

public static unsafe class AtbBulk
{
    // "class Face" of the SDK: DWORD v[3]; DWORD smGroup; DWORD flags;
    [StructLayout(LayoutKind.Sequential)]
    struct Face { public uint a, b, c, smGroup, flags; }

    // a map vert: which mesh vert it sits on, and its value
    struct Key : IEquatable<Key>
    {
        public int vertex;
        public float x, y, z;
        public bool Equals(Key other) { return vertex == other.vertex && x == other.x && y == other.y && z == other.z; }
        public override bool Equals(object other) { return other is Key && Equals((Key)other); }
        public override int GetHashCode()
        {
            unchecked { return ((vertex * 397 ^ x.GetHashCode()) * 397 ^ y.GetHashCode()) * 397 ^ z.GetHashCode(); }
        }
    }

    // the mesh being built: set by Begin, used by Uv and Data
    static int sHandle, sVertCount, sTriCount;
    static int* sPoints;            // per mesh vertex: the p3d point it stands for
    static int* sTris;              // per triangle: its three mesh vertices
    static int* sTriFace;           // per triangle: the p3d face it is part of, -1 for none
    static sbyte* sTriCorners;      // per triangle: which three corners of that face

    static IMesh MeshOf(int handle)
    {
        IINode node = GlobalInterface.Instance.COREInterface.GetINodeByHandle((uint)handle);
        if (node == null) throw new Exception("there is no node with this handle");
        ITriObject tri = node.ObjectRef as ITriObject;
        if (tri == null) throw new Exception("the node is not an Editable Mesh");
        return tri.Mesh;
    }

    static void* At(string address) { return (void*)long.Parse(address); }

    // verts: 3 floats per vert; tris: 3 ints per tri; smoothing, flags: a uint per tri
    public static int Geometry(int handle, string verts, int vertCount, string tris, int triCount,
                               string smoothing, string flags)
    {
        IMesh mesh = MeshOf(handle);
        mesh.SetNumVerts(vertCount, false, false);
        mesh.SetNumFaces(triCount, false, false);
        if (vertCount > 0)
            Buffer.MemoryCopy(At(verts), (void*)mesh.GetVertPtr(0).NativePointer, 12L * vertCount, 12L * vertCount);
        if (triCount > 0)
        {
            int* t = (int*)At(tris);
            uint* s = (uint*)At(smoothing);
            uint* f = (uint*)At(flags);
            Face* face = (Face*)mesh.GetFacePtr(0).NativePointer;
            for (int i = 0; i < triCount; i++)
            {
                face[i].a = (uint)t[3 * i];
                face[i].b = (uint)t[3 * i + 1];
                face[i].c = (uint)t[3 * i + 2];
                face[i].smGroup = s[i];
                face[i].flags = f[i];
            }
        }
        mesh.InvalidateGeomCache();
        mesh.InvalidateTopologyCache();
        return mesh.NumFaces;
    }

    static void Write(int handle, int channel, float[] verts, int vertCount, int[] tris, int triCount)
    {
        IMesh mesh = MeshOf(handle);
        if (triCount != mesh.NumFaces) throw new Exception("a map channel needs a map face per face of the mesh");
        if (mesh.NumMaps <= channel) mesh.SetNumMaps(channel + 1, true);
        mesh.SetMapSupport(channel, true);
        mesh.SetNumMapVerts(channel, vertCount, false);
        IMeshMap map = mesh.Map(channel);
        if (vertCount > 0)
            fixed (float* source = verts)
                Buffer.MemoryCopy(source, (void*)map.Tv.NativePointer, 12L * vertCount, 12L * vertCount);
        if (triCount > 0)
            fixed (int* source = tris)
                Buffer.MemoryCopy(source, (void*)map.Tf.NativePointer, 12L * triCount, 12L * triCount);
    }

    // a ready-made map channel: 3 floats per map vert, 3 ints per tri of the mesh
    public static int Channel(int handle, int channel, string verts, int vertCount, string tris, int triCount)
    {
        float[] v = new float[3 * vertCount];
        int[] t = new int[3 * triCount];
        if (vertCount > 0) Marshal.Copy((IntPtr)At(verts), v, 0, v.Length);
        if (triCount > 0) Marshal.Copy((IntPtr)At(tris), t, 0, t.Length);
        Write(handle, channel, v, vertCount, t, triCount);
        return vertCount;
    }

    public static int Begin(int handle, string points, int vertCount, string tris, string triFace,
                            string triCorners, int triCount)
    {
        sHandle = handle;
        sVertCount = vertCount;
        sTriCount = triCount;
        sPoints = (int*)At(points);
        sTris = (int*)At(tris);
        sTriFace = (int*)At(triFace);
        sTriCorners = (sbyte*)At(triCorners);
        return 0;
    }

    // A UV set
    public static int Uv(int channel, string uvs, string faceOffset)
    {
        float* uv = (float*)At(uvs);
        int* offset = (int*)At(faceOffset);
        Dictionary<Key, int> index = new Dictionary<Key, int>(sVertCount + sVertCount / 2);
        List<float> verts = new List<float>(3 * (sVertCount + sVertCount / 2));
        int[] tris = new int[3 * sTriCount];
        Key key = new Key();
        for (int t = 0; t < sTriCount; t++)
        {
            int face = sTriFace[t];
            for (int k = 0; k < 3; k++)
            {
                float u = 0f, v = 0f;
                if (face >= 0)
                {
                    int corner = offset[face] + sTriCorners[3 * t + k];
                    u = uv[2 * corner];
                    v = uv[2 * corner + 1];
                }
                key.vertex = sTris[3 * t + k];
                key.x = u == 0f ? 0f : u;           // -0 and 0 are one value
                key.y = v == 0f ? 0f : v;
                int found;
                if (!index.TryGetValue(key, out found))
                {
                    found = index.Count;
                    index.Add(key, found);
                    verts.Add(u);
                    verts.Add((float)(1.0 - (double)v));
                    verts.Add(0f);
                }
                tris[3 * t + k] = found;
            }
        }
        Write(sHandle, channel, verts.ToArray(), index.Count, tris, sTriCount);
        return index.Count;
    }

    // A data channel
    public static int Data(int channel, string p0, string p1, string p2, string f0, string f1, string f2)
    {
        double* P0 = (double*)At(p0), P1 = (double*)At(p1), P2 = (double*)At(p2);
        double* F0 = (double*)At(f0), F1 = (double*)At(f1), F2 = (double*)At(f2);
        int count = sVertCount;
        float[] first = new float[3 * count];
        bool[] has = new bool[count];
        List<float> extra = new List<float>();
        Dictionary<Key, int> extraIndex = new Dictionary<Key, int>();
        int[] tris = new int[3 * sTriCount];
        Key key = new Key();
        for (int t = 0; t < sTriCount; t++)
        {
            int face = sTriFace[t];
            double a0 = (F0 != null && face >= 0) ? F0[face] : 0.0;
            double a1 = (F1 != null && face >= 0) ? F1[face] : 0.0;
            double a2 = (F2 != null && face >= 0) ? F2[face] : 0.0;
            for (int k = 0; k < 3; k++)
            {
                int vertex = sTris[3 * t + k];
                int point = sPoints[vertex];
                float x = (float)((P0 != null ? P0[point] : 0.0) + a0);
                float y = (float)((P1 != null ? P1[point] : 0.0) + a1);
                float z = (float)((P2 != null ? P2[point] : 0.0) + a2);
                int found = vertex;
                if (!has[vertex])
                {
                    has[vertex] = true;
                    first[3 * vertex] = x;
                    first[3 * vertex + 1] = y;
                    first[3 * vertex + 2] = z;
                }
                else if (first[3 * vertex] != x || first[3 * vertex + 1] != y || first[3 * vertex + 2] != z)
                {
                    key.vertex = vertex;
                    key.x = x == 0f ? 0f : x;
                    key.y = y == 0f ? 0f : y;
                    key.z = z == 0f ? 0f : z;
                    if (!extraIndex.TryGetValue(key, out found))
                    {
                        found = count + extraIndex.Count;
                        extraIndex.Add(key, found);
                        extra.Add(x);
                        extra.Add(y);
                        extra.Add(z);
                    }
                }
                tris[3 * t + k] = found;
            }
        }
        float[] verts = first;
        if (extra.Count > 0)
        {
            verts = new float[first.Length + extra.Count];
            Array.Copy(first, verts, first.Length);
            extra.CopyTo(verts, first.Length);
        }
        Write(sHandle, channel, verts, verts.Length / 3, tris, sTriCount);
        return verts.Length / 3;
    }

    // The two heavy steps of preparing a mesh, as atb_p3d does them in Python (meshprep

    static int Find(int[] parent, int corner)
    {
        int root = corner;
        while (parent[root] != root) root = parent[root];
        while (parent[corner] != root) { int up = parent[corner]; parent[corner] = root; corner = up; }
        return root;
    }

    // (from, to) -> the face corners an edge starts at in that direction, in order of appearance
    class Edges
    {
        public Dictionary<long, int> index;
        public List<long> key = new List<long>();
        public List<int> head = new List<int>(), tail = new List<int>(), count = new List<int>();
        public int[] next, faceOf;

        public Edges(int* points, int* start, int faceCount, long pointCount)
        {
            int total = start[faceCount];
            index = new Dictionary<long, int>(total);
            next = new int[total];
            faceOf = new int[total];
            for (int k = 0; k < faceCount; k++)
            {
                int first = start[k], n = start[k + 1] - first;
                for (int i = 0; i < n; i++)
                {
                    int corner = first + i;
                    faceOf[corner] = k;
                    next[corner] = -1;
                    long edge = (long)points[corner] * pointCount + points[first + (i + 1) % n];
                    int e;
                    if (index.TryGetValue(edge, out e)) { next[tail[e]] = corner; tail[e] = corner; count[e]++; }
                    else { index.Add(edge, key.Count); key.Add(edge); head.Add(corner); tail.Add(corner); count.Add(1); }
                }
            }
        }
    }

    static bool SamePolygon(int* points, int* start, int one, int other)
    {
        int shared = 0;
        for (int i = start[one]; i < start[one + 1]; i++)
            for (int j = start[other]; j < start[other + 1]; j++)
                if (points[i] == points[j]) shared++;
        return shared >= 3;
    }

    static void JoinAcross(int[] parent, int* start, int[] faceOf, int forward, int backward)
    {
        // forward runs low -> high from its corner, backward high -> low from its corner
        int k1 = faceOf[forward], k2 = faceOf[backward];
        int n1 = start[k1 + 1] - start[k1], n2 = start[k2 + 1] - start[k2];
        int a = Find(parent, forward), b = Find(parent, start[k2] + (backward - start[k2] + 1) % n2);
        if (a != b) parent[b] = a;
        a = Find(parent, start[k1] + (forward - start[k1] + 1) % n1);
        b = Find(parent, backward);
        if (a != b) parent[b] = a;
    }

    // positions: 3 doubles per p3d point
    public static int Sheets(string facePoints, string faceStart, int faceCount, string positions, int pointCount,
                             string cornerVertex, string vertexPoint)
    {
        int* points = (int*)At(facePoints);
        int* start = (int*)At(faceStart);
        double* position = (double*)At(positions);
        int* outCorner = (int*)At(cornerVertex);
        int* outPoint = (int*)At(vertexPoint);
        int total = start[faceCount];
        int[] parent = new int[total];
        for (int i = 0; i < total; i++) parent[i] = i;
        Edges edges = new Edges(points, start, faceCount, pointCount);
        int[] faceOf = edges.faceOf;
        double[] normal = null;
        bool[] hasNormal = null;
        List<double> alike = new List<double>();
        List<int> pairForward = new List<int>(), pairBackward = new List<int>();
        HashSet<int> taken = new HashSet<int>();

        for (int e = 0; e < edges.key.Count; e++)
        {
            long low = edges.key[e] / pointCount, high = edges.key[e] % pointCount;
            if (low > high) continue;
            int r;
            if (!edges.index.TryGetValue(high * pointCount + low, out r)) continue;
            if (edges.count[e] == 1 && edges.count[r] == 1)
            {
                int f = edges.head[e], b = edges.head[r];
                if (!SamePolygon(points, start, faceOf[f], faceOf[b])) JoinAcross(parent, start, faceOf, f, b);
                continue;
            }
            // more faces on the edge: pair each with the one facing most nearly the same way
            if (normal == null) { normal = new double[3 * faceCount]; hasNormal = new bool[faceCount]; }
            alike.Clear(); pairForward.Clear(); pairBackward.Clear();
            for (int f = edges.head[e]; f != -1; f = edges.next[f])
                for (int b = edges.head[r]; b != -1; b = edges.next[b])
                {
                    int kf = faceOf[f], kb = faceOf[b];
                    if (SamePolygon(points, start, kf, kb)) continue;
                    for (int pass = 0; pass < 2; pass++)
                    {
                        int k = pass == 0 ? kf : kb;
                        if (hasNormal[k]) continue;
                        double x = 0.0, y = 0.0, z = 0.0;                    // Newell's method
                        int first = start[k], n = start[k + 1] - first;
                        for (int i = 0; i < n; i++)
                        {
                            double* p = position + 3 * points[first + i];
                            double* q = position + 3 * points[first + (i + 1) % n];
                            x += (p[1] - q[1]) * (p[2] + q[2]);
                            y += (p[2] - q[2]) * (p[0] + q[0]);
                            z += (p[0] - q[0]) * (p[1] + q[1]);
                        }
                        double length = Math.Sqrt(x * x + y * y + z * z);
                        if (length == 0.0) length = 1.0;
                        normal[3 * k] = x / length; normal[3 * k + 1] = y / length; normal[3 * k + 2] = z / length;
                        hasNormal[k] = true;
                    }
                    alike.Add(normal[3 * kf] * normal[3 * kb] + normal[3 * kf + 1] * normal[3 * kb + 1]
                              + normal[3 * kf + 2] * normal[3 * kb + 2]);
                    pairForward.Add(f);
                    pairBackward.Add(b);
                }
            int pairs = alike.Count;
            int[] order = new int[pairs];
            for (int i = 0; i < pairs; i++)                                 // stable, most alike first
            {
                int at = i;
                while (at > 0 && alike[order[at - 1]] < alike[i]) { order[at] = order[at - 1]; at--; }
                order[at] = i;
            }
            taken.Clear();
            for (int i = 0; i < pairs; i++)
            {
                int f = pairForward[order[i]], b = pairBackward[order[i]];
                if (taken.Contains(f) || taken.Contains(b)) continue;
                taken.Add(f); taken.Add(b);
                JoinAcross(parent, start, faceOf, f, b);
            }
        }

        // a vert per fan; verts of one point next to each other, points in order
        int[] root = new int[total];
        bool[] seen = new bool[total];
        int[] perPoint = new int[pointCount + 1];
        List<int> fans = new List<int>();
        for (int corner = 0; corner < total; corner++)
        {
            int found = Find(parent, corner);
            root[corner] = found;
            if (!seen[found]) { seen[found] = true; fans.Add(corner); perPoint[points[corner] + 1]++; }
        }
        for (int point = 0; point < pointCount; point++) perPoint[point + 1] += perPoint[point];
        int[] vertexOfRoot = new int[total];
        foreach (int corner in fans)
        {
            int point = points[corner];
            int vertex = perPoint[point]++;
            vertexOfRoot[root[corner]] = vertex;
            outPoint[vertex] = point;
        }
        for (int corner = 0; corner < total; corner++) outCorner[corner] = vertexOfRoot[root[corner]];
        return fans.Count;
    }

    static void JoinFaces(int[] parent, int* points, int* start, int one, int other)
    {
        // the two faces shade together: join their corners at every point they share
        for (int i = start[one]; i < start[one + 1]; i++)
            for (int j = start[other]; j < start[other + 1]; j++)
                if (points[i] == points[j])
                {
                    int a = Find(parent, i), b = Find(parent, j);
                    if (a != b) parent[b] = a;
                }
    }

    static bool Fits(Dictionary<int, int> fanAt, int* points, int* start, int[] fanOf, int face)
    {
        for (int corner = start[face]; corner < start[face + 1]; corner++)
        {
            int held;
            if (fanAt.TryGetValue(points[corner], out held) && held != fanOf[corner]) return false;
        }
        return true;
    }

    static void Hold(Dictionary<int, int> fanAt, int* points, int* start, int[] fanOf, int face)
    {
        for (int corner = start[face]; corner < start[face + 1]; corner++) fanAt[points[corner]] = fanOf[corner];
    }

    // sharp: pairs of p3d points
    public static int Smoothing(string facePoints, string faceStart, int faceCount, int pointCount,
                                string sharp, int sharpCount, string groupsOut)
    {
        int* points = (int*)At(facePoints);
        int* start = (int*)At(faceStart);
        int* sharpPairs = (int*)At(sharp);
        uint* groups = (uint*)At(groupsOut);
        long pc = pointCount;
        for (int f = 0; f < faceCount; f++) groups[f] = 0;
        HashSet<long> sharpSet = new HashSet<long>();
        for (int i = 0; i < sharpCount; i++)
        {
            long a = sharpPairs[2 * i], b = sharpPairs[2 * i + 1];
            sharpSet.Add(a < b ? a * pc + b : b * pc + a);
        }
        int total = start[faceCount];
        Edges edges = new Edges(points, start, faceCount, pc);
        int[] faceOf = edges.faceOf;
        int[] parent = new int[total];
        for (int i = 0; i < total; i++) parent[i] = i;
        List<int>[] neighbours = new List<int>[faceCount];
        List<int> pairF = new List<int>(), pairG = new List<int>();
        HashSet<long> seenPair = new HashSet<long>();
        for (int e = 0; e < edges.key.Count; e++)
        {
            long a = edges.key[e] / pc, b = edges.key[e] % pc;
            if (a >= b || sharpSet.Contains(edges.key[e])) continue;
            int r;
            if (!edges.index.TryGetValue(b * pc + a, out r)) continue;
            for (int cf = edges.head[e]; cf != -1; cf = edges.next[cf])
                for (int cg = edges.head[r]; cg != -1; cg = edges.next[cg])
                {
                    int f = faceOf[cf], g = faceOf[cg];
                    if (f == g) continue;
                    long pair = f < g ? (long)f * faceCount + g : (long)g * faceCount + f;
                    if (!seenPair.Add(pair)) continue;
                    pairF.Add(f < g ? f : g);
                    pairG.Add(f < g ? g : f);
                    if (neighbours[f] == null) neighbours[f] = new List<int>();
                    if (neighbours[g] == null) neighbours[g] = new List<int>();
                    neighbours[f].Add(g);
                    neighbours[g].Add(f);
                    JoinFaces(parent, points, start, f, g);
                }
        }
        if (pairF.Count == 0) return 0;
        int[] fanOf = new int[total];
        for (int corner = 0; corner < total; corner++) fanOf[corner] = Find(parent, corner);

        // 1. regions: smooth surfaces w/o a crease inside
        int[] region = new int[faceCount];
        for (int f = 0; f < faceCount; f++) region[f] = -1;
        List<Dictionary<int, int>> regionFans = new List<Dictionary<int, int>>();
        List<List<int>> regionFaces = new List<List<int>>();
        List<int> stack = new List<int>();
        for (int seed = 0; seed < faceCount; seed++)
        {
            if (region[seed] != -1 || neighbours[seed] == null) continue;
            int current = regionFans.Count;
            Dictionary<int, int> held = new Dictionary<int, int>();
            Hold(held, points, start, fanOf, seed);
            List<int> members = new List<int>();
            members.Add(seed);
            region[seed] = current;
            stack.Clear();
            stack.Add(seed);
            while (stack.Count > 0)
            {
                int face = stack[stack.Count - 1];
                stack.RemoveAt(stack.Count - 1);
                List<int> around = neighbours[face];
                for (int i = 0; i < around.Count; i++)
                {
                    int candidate = around[i];
                    if (region[candidate] != -1 || !Fits(held, points, start, fanOf, candidate)) continue;
                    region[candidate] = current;
                    members.Add(candidate);
                    stack.Add(candidate);
                    Hold(held, points, start, fanOf, candidate);
                }
            }
            regionFans.Add(held);
            regionFaces.Add(members);
        }

        // 2. regions into bits, the biggest first, as many per bit as don't clash
        int regionCount = regionFans.Count;
        int[] waiting = new int[regionCount];
        for (int i = 0; i < regionCount; i++) waiting[i] = i;
        Array.Sort(waiting, delegate(int x, int y)
        {
            int bySize = regionFaces[y].Count.CompareTo(regionFaces[x].Count);
            return bySize != 0 ? bySize : x.CompareTo(y);
        });
        List<Dictionary<int, int>> bitFans = new List<Dictionary<int, int>>();
        List<int> queue = new List<int>(waiting);
        while (queue.Count > 0 && bitFans.Count < 32)
        {
            uint mask = 1u << bitFans.Count;
            Dictionary<int, int> fanAt = new Dictionary<int, int>();
            List<int> left = new List<int>();
            foreach (int index in queue)
            {
                Dictionary<int, int> held = regionFans[index];
                bool clash = false;
                foreach (KeyValuePair<int, int> item in held)
                {
                    int there;
                    if (fanAt.TryGetValue(item.Key, out there) && there != item.Value) { clash = true; break; }
                }
                if (clash) { left.Add(index); continue; }
                foreach (KeyValuePair<int, int> item in held) fanAt[item.Key] = item.Value;
                foreach (int face in regionFaces[index]) groups[face] |= mask;
            }
            bitFans.Add(fanAt);
            queue = left;
        }

        // 3. smooth pairs that don't share a bit yet
        int unsolved = 0;
        List<int> open = new List<int>();
        for (int i = 0; i < pairF.Count; i++)
            if ((groups[pairF[i]] & groups[pairG[i]]) == 0) open.Add(i);
        foreach (int i in open)
        {
            int f = pairF[i], g = pairG[i];
            if ((groups[f] & groups[g]) != 0) continue;
            bool done = false;
            for (int bit = 0; bit < bitFans.Count && !done; bit++)
            {
                uint mask = 1u << bit;
                bool inF = (groups[f] & mask) != 0, inG = (groups[g] & mask) != 0;
                Dictionary<int, int> fanAt = bitFans[bit];
                if ((inF || Fits(fanAt, points, start, fanOf, f)) && (inG || Fits(fanAt, points, start, fanOf, g)))
                {
                    if (!inF) { groups[f] |= mask; Hold(fanAt, points, start, fanOf, f); }
                    if (!inG) { groups[g] |= mask; Hold(fanAt, points, start, fanOf, g); }
                    done = true;
                }
            }
            if (done) continue;
            if (bitFans.Count < 32)
            {
                uint mask = 1u << bitFans.Count;
                Dictionary<int, int> fanAt = new Dictionary<int, int>();
                bitFans.Add(fanAt);
                groups[f] |= mask; Hold(fanAt, points, start, fanOf, f);
                groups[g] |= mask; Hold(fanAt, points, start, fanOf, g);
            }
            else unsolved++;
        }
        if (unsolved == 0) return 0;

        // How many points do the groups shade differently? Fans as the groups make them
        int[] other = new int[total];
        for (int i = 0; i < total; i++) other[i] = i;
        for (int e = 0; e < edges.key.Count; e++)
        {
            long a = edges.key[e] / pc, b = edges.key[e] % pc;
            if (a >= b) continue;
            int r;
            if (!edges.index.TryGetValue(b * pc + a, out r)) continue;
            bool sharpHere = false;
            for (int cf = edges.head[e]; cf != -1 && !sharpHere; cf = edges.next[cf])
                for (int cg = edges.head[r]; cg != -1; cg = edges.next[cg])
                {
                    int f = faceOf[cf], g = faceOf[cg];
                    if (f != g && (groups[f] & groups[g]) == 0) { sharpHere = true; break; }
                }
            if (sharpHere) continue;
            for (int cf = edges.head[e]; cf != -1; cf = edges.next[cf])
                for (int cg = edges.head[r]; cg != -1; cg = edges.next[cg])
                    if (faceOf[cf] != faceOf[cg]) JoinFaces(other, points, start, faceOf[cf], faceOf[cg]);
        }
        Dictionary<int, int> there2 = new Dictionary<int, int>(), back = new Dictionary<int, int>();
        HashSet<int> wrong = new HashSet<int>();
        for (int corner = 0; corner < total; corner++)
        {
            int a = fanOf[corner], b = Find(other, corner), found;
            if (there2.TryGetValue(a, out found)) { if (found != b) wrong.Add(points[corner]); }
            else there2.Add(a, b);
            if (back.TryGetValue(b, out found)) { if (found != a) wrong.Add(points[corner]); }
            else back.Add(b, a);
        }
        return wrong.Count;
    }

    // Reading an Editable Poly, for the export

    const int FaceDeg = 8, FaceVtx = 16, FaceSmGroup = 40, FaceMaterial = 44;   // MNFace
    const int VertPoint = 4;                                                    // MNVert
    const int MapFaceDeg = 4, MapFaceTv = 8;                                    // MNMapFace

    static IMNMesh PolyOf(int handle)
    {
        IINode node = GlobalInterface.Instance.COREInterface.GetINodeByHandle((uint)handle);
        if (node == null) throw new Exception("there is no node with this handle");
        IPolyObject poly = node.ObjectRef as IPolyObject;
        if (poly == null) throw new Exception("the node is not an Editable Poly");
        return poly.Mm;
    }

    static byte* Faces(IMNMesh mm, out long stride)
    {
        byte* first = (byte*)mm.F(0).NativePointer;
        stride = mm.FNum > 1 ? (byte*)mm.F(1).NativePointer - first : 0;
        return first;
    }

    static byte* Verts(IMNMesh mm, out long stride)
    {
        byte* first = (byte*)mm.V(0).NativePointer;
        stride = mm.VNum > 1 ? (byte*)mm.V(1).NativePointer - first : 0;
        return first;
    }

    // "verts faces corners deadVertices deadFaces mapChannels"
    public static string PolyInfo(int handle)
    {
        IMNMesh mm = PolyOf(handle);
        int vertCount = mm.VNum, faceCount = mm.FNum;
        long corners = 0, stride;
        if (faceCount > 0)
        {
            byte* first = Faces(mm, out stride);
            int[] probes = new int[] { 0, 1, faceCount / 2, faceCount - 1 };
            foreach (int i in probes)
            {
                if (i >= faceCount) continue;
                IMNFace face = mm.F(i);
                byte* p = first + stride * i;
                bool same = *(int*)(p + FaceDeg) == face.Deg && *(uint*)(p + FaceSmGroup) == face.SmGroup
                            && *(ushort*)(p + FaceMaterial) == face.Material;
                for (int k = 0; same && k < face.Deg; k++) same = (*(int**)(p + FaceVtx))[k] == face.Vtx[k];
                if (!same) throw new Exception("the faces of an Editable Poly are not laid out as expected");
            }
            for (int i = 0; i < faceCount; i++) corners += *(int*)(first + stride * i + FaceDeg);
        }
        if (vertCount > 0)
        {
            byte* first = Verts(mm, out stride);
            int[] probes = new int[] { 0, 1, vertCount / 2, vertCount - 1 };
            foreach (int i in probes)
            {
                if (i >= vertCount) continue;
                IPoint3 q = mm.P(i);
                float* p = (float*)(first + stride * i + VertPoint);
                if (p[0] != q.X || p[1] != q.Y || p[2] != q.Z)
                    throw new Exception("the vertices of an Editable Poly are not laid out as expected");
            }
        }
        return vertCount + " " + faceCount + " " + corners + " " + mm.NumDeadVerts + " " + mm.NumDeadFaces + " " + mm.MNum;
    }

    // matrix: 12 floats, the rows of the object's transform ("0": none)
    public static int PolyGeometry(int handle, string matrix, string outVerts, string outDeg, string outVtx,
                                   string outSmoothing, string outMaterial)
    {
        IMNMesh mm = PolyOf(handle);
        int vertCount = mm.VNum, faceCount = mm.FNum;
        float* m = (float*)At(matrix);
        float* verts = (float*)At(outVerts);
        long stride;
        if (vertCount > 0)
        {
            byte* first = Verts(mm, out stride);
            for (int i = 0; i < vertCount; i++)
            {
                float* p = (float*)(first + stride * i + VertPoint);
                float x = p[0], y = p[1], z = p[2];
                if (m != null)
                {
                    float tx = x * m[0] + y * m[3] + z * m[6] + m[9];
                    float ty = x * m[1] + y * m[4] + z * m[7] + m[10];
                    float tz = x * m[2] + y * m[5] + z * m[8] + m[11];
                    x = tx; y = ty; z = tz;
                }
                verts[3 * i] = x; verts[3 * i + 1] = y; verts[3 * i + 2] = z;
            }
        }
        int* deg = (int*)At(outDeg);
        int* vtx = (int*)At(outVtx);
        uint* smoothing = (uint*)At(outSmoothing);
        int* material = (int*)At(outMaterial);
        int at = 0;
        if (faceCount > 0)
        {
            byte* first = Faces(mm, out stride);
            for (int i = 0; i < faceCount; i++)
            {
                byte* p = first + stride * i;
                int count = *(int*)(p + FaceDeg);
                int* source = *(int**)(p + FaceVtx);
                deg[i] = count;
                for (int k = 0; k < count; k++) vtx[at++] = source[k];
                smoothing[i] = *(uint*)(p + FaceSmGroup);
                material[i] = *(ushort*)(p + FaceMaterial) + 1;
            }
        }
        return at;
    }

    // the nr of map verts of a channel the object has
    public static int PolyChannelSize(int handle, int channel)
    {
        IMNMesh mm = PolyOf(handle);
        if (channel >= mm.MNum) return -1;
        IMNMap map = mm.M(channel);
        if (map.FNum != mm.FNum) throw new Exception("a map channel of an Editable Poly does not have a map face per face");
        return map.VNum;
    }

    // Writes the map verts (3 floats each) and the map verts of all face corners in a row
    public static int PolyChannel(int handle, int channel, string outVerts, string outFaces)
    {
        IMNMesh mm = PolyOf(handle);
        IMNMap map = mm.M(channel);
        int vertCount = map.VNum, faceCount = map.FNum;
        if (faceCount != mm.FNum) throw new Exception("a map channel of an Editable Poly does not have a map face per face");
        if (vertCount > 0)
        {
            float* source = (float*)map.V_.NativePointer;
            IPoint3 q = map.V(vertCount - 1);
            float* last = source + 3 * (vertCount - 1);
            if (last[0] != q.X || last[1] != q.Y || last[2] != q.Z)
                throw new Exception("the map vertices of an Editable Poly are not laid out as expected");
            Buffer.MemoryCopy(source, At(outVerts), 12L * vertCount, 12L * vertCount);
        }
        int* faces = (int*)At(outFaces);
        int at = 0;
        if (faceCount > 0)
        {
            long stride, faceStride;
            byte* meshFaces = Faces(mm, out faceStride);
            byte* first = (byte*)map.F(0).NativePointer;
            stride = faceCount > 1 ? (byte*)map.F(1).NativePointer - first : 0;
            int[] probes = new int[] { 0, faceCount - 1 };
            foreach (int i in probes)
            {
                IMNMapFace face = map.F(i);
                byte* p = first + stride * i;
                if (*(int*)(p + MapFaceDeg) != face.Deg || *(IntPtr*)(p + MapFaceTv) != face.Tv)
                    throw new Exception("the map faces of an Editable Poly are not laid out as expected");
            }
            for (int i = 0; i < faceCount; i++)
            {
                byte* p = first + stride * i;
                int count = *(int*)(p + MapFaceDeg);
                if (count != *(int*)(meshFaces + faceStride * i + FaceDeg))
                    throw new Exception("a map face of an Editable Poly has another number of corners than its face");
                int* source = *(int**)(p + MapFaceTv);
                for (int k = 0; k < count; k++) faces[at++] = source[k];
            }
        }
        return at;
    }

    // Normals the way Object Builder computes them: atb_p3d/normals.py compute() is the reference.
    // Points flagged "angle normal" are left to the Python code (acos may differ in the last bit).
    const uint LightMask = 0x3000A7, BothSides = 0x20, Sky = 0x80, Reverse = 0x100000, Flat = 0x200000;
    const uint LockNormal = 0x2000000;

    static int CornerOf(int* points, int* start, int face, int point)
    {
        for (int corner = start[face]; corner < start[face + 1]; corner++)
            if (points[corner] == point) return corner;
        return -1;
    }

    static void Normalize(double* v)
    {
        double length = Math.Sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
        if (length > 0.0) { v[0] = v[0] / length; v[1] = v[1] / length; v[2] = v[2] / length; }
        else { v[0] = 0.0; v[1] = 0.0; v[2] = 0.0; }
    }

    // positions, locked: 3 doubles per point. Writes the normal index of every face corner and
    // the normals (3 doubles each; room for corners + faces + 1); returns the number of normals.
    public static int Normals(string facePoints, string faceStart, int faceCount, string positions, int pointCount,
                              string pointFlags, string faceFlags, string sharp, int sharpCount, string locked,
                              string outIndices, string outNormals)
    {
        int* points = (int*)At(facePoints);
        int* start = (int*)At(faceStart);
        double* position = (double*)At(positions);
        uint* pointFlag = (uint*)At(pointFlags);
        uint* faceFlag = (uint*)At(faceFlags);
        int* sharpPairs = (int*)At(sharp);
        double* lockedNormal = (double*)At(locked);
        int* indices = (int*)At(outIndices);
        double* normals = (double*)At(outNormals);
        long pc = pointCount;
        int total = start[faceCount];
        int count = 0;
        for (int i = 0; i < total; i++) indices[i] = 0;

        uint[] light = new uint[faceCount];
        bool[] special = new bool[faceCount];
        for (int f = 0; f < faceCount; f++)
        {
            light[f] = faceFlag[f] & LightMask;
            special[f] = light[f] == BothSides || light[f] == Sky || light[f] == Flat;
        }
        HashSet<long> sharpSet = new HashSet<long>();
        for (int i = 0; i < sharpCount; i++)
        {
            long a = sharpPairs[2 * i], b = sharpPairs[2 * i + 1];
            sharpSet.Add(a < b ? a * pc + b : b * pc + a);
        }

        // faces around each point, the ordinary-lit ones, in face order
        int[] first = new int[pointCount + 1];
        int[] lastFace = new int[pointCount];
        for (int p = 0; p < pointCount; p++) lastFace[p] = -1;
        for (int f = 0; f < faceCount; f++)
        {
            if (special[f]) continue;
            for (int corner = start[f]; corner < start[f + 1]; corner++)
                if (lastFace[points[corner]] != f) { lastFace[points[corner]] = f; first[points[corner] + 1]++; }
        }
        for (int p = 0; p < pointCount; p++) first[p + 1] += first[p];
        int[] around = new int[first[pointCount]];
        int[] fill = new int[pointCount];
        for (int p = 0; p < pointCount; p++) lastFace[p] = -1;
        for (int f = 0; f < faceCount; f++)
        {
            if (special[f]) continue;
            for (int corner = start[f]; corner < start[f + 1]; corner++)
            {
                int p = points[corner];
                if (lastFace[p] != f) { lastFace[p] = f; around[first[p] + fill[p]++] = f; }
            }
        }

        // neighbours across edges that are not sharp, running along them in opposite directions
        List<int>[] graph = new List<int>[faceCount];
        for (int f = 0; f < faceCount; f++)
        {
            int begin = start[f], n = start[f + 1] - begin;
            for (int j = 0; j < n; j++)
            {
                int point = points[begin + j];
                int following = points[begin + (j + 1 < n ? j + 1 : 0)];
                long edge = point < following ? point * pc + following : following * pc + point;
                if (sharpSet.Contains(edge)) continue;
                for (int k = first[point]; k < first[point + 1]; k++)
                {
                    int other = around[k];
                    if (other == f) continue;
                    int at = CornerOf(points, start, other, point);
                    int before = at > start[other] ? at - 1 : start[other + 1] - 1;
                    if (points[before] != following) continue;
                    if (graph[f] == null) graph[f] = new List<int>();
                    if (!graph[f].Contains(other)) graph[f].Add(other);
                }
            }
        }

        bool[] visited = new bool[total];           // by the first corner of a face at a point
        Dictionary<int, int> reserved = new Dictionary<int, int>();
        List<int> stack = new List<int>();
        for (int f = 0; f < faceCount; f++)
        {
            int begin = start[f], n = start[f + 1] - begin;
            if (n < 3) continue;
            if (n == 3 && (points[begin] == points[begin + 1] || points[begin] == points[begin + 2]
                           || points[begin + 1] == points[begin + 2])) continue;
            uint kind = light[f];
            if (kind == BothSides)
            {
                for (int j = 0; j < n; j++)
                {
                    double* before = position + 3 * points[begin + (j > 0 ? j - 1 : n - 1)];
                    double* here = position + 3 * points[begin + j];
                    double* after = position + 3 * points[begin + (j + 1) % n];
                    indices[begin + j] = count;
                    for (int k = 0; k < 3; k++) normals[3 * count + k] = (before[k] + after[k]) * 0.5 - here[k];
                    count++;
                }
            }
            else if (kind == Sky)
            {
                for (int j = 0; j < n; j++)
                {
                    double* here = position + 3 * points[begin + j];
                    indices[begin + j] = count;
                    normals[3 * count] = here[0]; normals[3 * count + 1] = here[1]; normals[3 * count + 2] = here[2];
                    Normalize(normals + 3 * count);
                    count++;
                }
            }
            else if (kind == Flat)
            {
                double x = 0.0, y = 0.0, z = 0.0;
                for (int j = 0; j < n; j++)
                {
                    double* p0 = position + 3 * points[begin + (j > 0 ? j - 1 : n - 1)];
                    double* p1 = position + 3 * points[begin + j];
                    double* p2 = position + 3 * points[begin + (j + 1) % n];
                    double ax = p1[0] - p0[0], ay = p1[1] - p0[1], az = p1[2] - p0[2];
                    double bx = p2[0] - p0[0], by = p2[1] - p0[1], bz = p2[2] - p0[2];
                    x += ay * bz - az * by;
                    y += az * bx - ax * bz;
                    z += ax * by - ay * bx;
                }
                for (int j = 0; j < n; j++) indices[begin + j] = count;
                normals[3 * count] = x; normals[3 * count + 1] = y; normals[3 * count + 2] = z;
                Normalize(normals + 3 * count);
                count++;
            }
            else
            {
                for (int j = 0; j < n; j++)
                {
                    int point = points[begin + j];
                    if ((pointFlag[point] & LockNormal) != 0)
                    {
                        int slot;
                        if (!reserved.TryGetValue(point, out slot))
                        {
                            slot = count++;
                            reserved.Add(point, slot);
                            normals[3 * slot] = 0.0; normals[3 * slot + 1] = 0.0; normals[3 * slot + 2] = 0.0;
                        }
                        indices[begin + j] = slot;
                        continue;
                    }
                    int own = CornerOf(points, start, f, point);
                    if (visited[own]) continue;
                    // the fan of faces around this point shares one normal
                    int fresh = count++;
                    normals[3 * fresh] = 0.0; normals[3 * fresh + 1] = 0.0; normals[3 * fresh + 2] = 0.0;
                    visited[own] = true;
                    stack.Clear();
                    stack.Add(f);
                    while (stack.Count > 0)
                    {
                        int face = stack[stack.Count - 1];
                        stack.RemoveAt(stack.Count - 1);
                        List<int> next = graph[face];
                        if (next == null) continue;
                        for (int k = 0; k < next.Count; k++)
                        {
                            int corner = CornerOf(points, start, next[k], point);
                            if (corner < 0) continue;
                            if (!visited[corner]) { visited[corner] = true; stack.Add(next[k]); }
                            indices[corner] = fresh;
                        }
                    }
                    indices[begin + j] = fresh;
                }
            }
        }

        if (count > 0)
            for (int f = 0; f < faceCount; f++)
            {
                if (special[f]) continue;
                int begin = start[f], n = start[f + 1] - begin;
                bool reverse = light[f] == Reverse;
                int alone = -1;
                for (int j = 0; j < n; j++)
                {
                    int point = points[begin + j];
                    double* here = position + 3 * point;
                    double* before = position + 3 * points[begin + (j > 0 ? j - 1 : n - 1)];
                    double* after = position + 3 * points[begin + (j + 1) % n];
                    double ax = before[0] - here[0], ay = before[1] - here[1], az = before[2] - here[2];
                    double bx = after[0] - here[0], by = after[1] - here[1], bz = after[2] - here[2];
                    double x = by * az - bz * ay, y = bz * ax - bx * az, z = bx * ay - by * ax;
                    if (reverse) { x = -x; y = -y; z = -z; }
                    int slot = indices[begin + j];
                    double* normal = normals + 3 * slot;
                    if ((pointFlag[point] & LockNormal) != 0)
                    {
                        normal[0] = lockedNormal[3 * point]; normal[1] = lockedNormal[3 * point + 1]; normal[2] = lockedNormal[3 * point + 2];
                        continue;
                    }
                    double sx = normal[0] + x, sy = normal[1] + y, sz = normal[2] + z;
                    if (sx * sx + sy * sy + sz * sz < 1e-12 && (normal[0] != 0.0 || normal[1] != 0.0 || normal[2] != 0.0))
                    {
                        if (alone == -1)
                        {
                            alone = count++;
                            normals[3 * alone] = x; normals[3 * alone + 1] = y; normals[3 * alone + 2] = z;
                        }
                        indices[begin + j] = alone;
                    }
                    else { normal[0] = sx; normal[1] = sy; normal[2] = sz; }
                }
            }
        for (int i = 0; i < count; i++) Normalize(normals + 3 * i);
        return count;
    }

    // Edges across which two faces facing each other share no smoothing group bit
    // (smoothing.sharp_edges). Writes pairs of points; returns how many.
    public static int SharpFromGroups(string facePoints, string faceStart, int faceCount, int pointCount,
                                      string groups, string outPairs)
    {
        int* points = (int*)At(facePoints);
        int* start = (int*)At(faceStart);
        uint* group = (uint*)At(groups);
        int* pairs = (int*)At(outPairs);
        long pc = pointCount;
        Edges edges = new Edges(points, start, faceCount, pc);
        int count = 0;
        for (int e = 0; e < edges.key.Count; e++)
        {
            long a = edges.key[e] / pc, b = edges.key[e] % pc;
            if (a >= b) continue;
            int r;
            if (!edges.index.TryGetValue(b * pc + a, out r)) continue;
            bool sharpHere = false;
            for (int cf = edges.head[e]; cf != -1 && !sharpHere; cf = edges.next[cf])
                for (int cg = edges.head[r]; cg != -1; cg = edges.next[cg])
                {
                    int f = edges.faceOf[cf], g = edges.faceOf[cg];
                    if (f != g && (group[f] & group[g]) == 0) { sharpHere = true; break; }
                }
            if (sharpHere) { pairs[2 * count] = (int)a; pairs[2 * count + 1] = (int)b; count++; }
        }
        return count;
    }

    static void Inside(int m, int mapCount, int v, int vertCount)
    {
        if (m < 0 || m >= mapCount || v < 0 || v >= vertCount)
            throw new Exception("a map face of an Editable Poly points outside its channel");
    }

    // One slot of a data channel, per vert and per face: reader._decode is the reference.
    // numeric: the first value met. Else the largest weight, and 1 per face when all its corners carry the face flag.
    public static int Slot(string mapVerts, int mapCount, string mapFaces, string faceVerts, string degrees,
                           int faceCount, int vertCount, int component, int numeric, string outVerts, string outFaces)
    {
        float* values = (float*)At(mapVerts);
        int* mapped = (int*)At(mapFaces);
        int* verts = (int*)At(faceVerts);
        int* degree = (int*)At(degrees);
        double* perVert = (double*)At(outVerts);
        double* perFace = (double*)At(outFaces);
        bool[] seen = new bool[vertCount];
        int at = 0;
        for (int f = 0; f < faceCount; f++)
        {
            bool flagged = true;
            double first = 0.0;
            for (int k = 0; k < degree[f]; k++, at++)
            {
                int m = mapped[at], v = verts[at];
                Inside(m, mapCount, v, vertCount);
                double value = values[3 * m + component];
                if (numeric != 0)
                {
                    if (k == 0) first = value;
                    if (!seen[v]) { seen[v] = true; perVert[v] = value; }
                    continue;
                }
                if (value >= 1.5) value -= 2.0; else flagged = false;
                if (!seen[v] || value > perVert[v]) { seen[v] = true; perVert[v] = value; }
            }
            perFace[f] = numeric != 0 ? first : (flagged ? 1.0 : 0.0);
        }
        return at;
    }

    // A layer channel: the group nr of every vert and of every face, 0 for none (registry.group_number)
    public static int Layer(string mapVerts, int mapCount, string mapFaces, string faceVerts, string degrees,
                            int faceCount, int vertCount, string outVerts, string outFaces)
    {
        float* values = (float*)At(mapVerts);
        int* mapped = (int*)At(mapFaces);
        int* verts = (int*)At(faceVerts);
        int* degree = (int*)At(degrees);
        int* perVert = (int*)At(outVerts);
        int* perFace = (int*)At(outFaces);
        int[] numbers = new int[mapCount];
        for (int m = 0; m < mapCount; m++)
        {
            double x = values[3 * m], y = values[3 * m + 1];
            if (!(x >= 0.5 && x < 2e9)) continue;
            int number = (int)Math.Round(x);
            if (number < 1 || Math.Abs(x - number) > 1e-4) continue;
            double expected = (float)((double)number * (double)number);
            if (Math.Abs(y - expected) <= 1e-6 * expected + 1e-6) numbers[m] = number;
        }
        int at = 0;
        for (int f = 0; f < faceCount; f++)
        {
            int first = 0;
            bool inside = false;
            for (int k = 0; k < degree[f]; k++, at++)
            {
                int m = mapped[at], v = verts[at];
                Inside(m, mapCount, v, vertCount);
                int number = numbers[m];
                if (k == 0) { first = number; inside = first != 0; }
                if (number != 0) perVert[v] = number;
                if (number != first || values[3 * m + 2] < 0.5f) inside = false;
            }
            perFace[f] = inside ? first : 0;
        }
        return at;
    }

    // the flags of the first faces, as 3ds Max itself sets them (used by the tests)
    public static string Flags(int handle, int count)
    {
        IMesh mesh = MeshOf(handle);
        Face* face = (Face*)mesh.GetFacePtr(0).NativePointer;
        string text = "";
        for (int i = 0; i < count && i < mesh.NumFaces; i++) text += face[i].flags.ToString() + " ";
        return text.Trim();
    }
}
