---
qa: manual
---

# Tests

A page says how the tree tests the code it walks. A test, here, is code the tree carries to exercise other code of the tree: a KUnit suite, a kselftest under `tools/testing/selftests/`, a test module, a driver's own selftests, or a user-space harness under `tools/testing/` that compiles the code under test.

For every test that calls a function the page walks, builds and checks a struct it walks, or drives a user-visible surface it walks, the page gives, in the subsection that walks that code and after the walk:

- the suite or program and the case, each linked to its definition line;
- what the case feeds in and what it expects, as the property of the walked code it pins down: a value for an input, an ordering, an error return, the state after a sequence;
- how the test reaches the code: a direct call, a symbol the code under test makes visible or exports for the test, a stub or redirect the code under test carries, a mock device or fixture the test builds, or the file, ioctl or syscall a user-space test drives;
- the Kconfig option that builds the test, with the value the page assumes for it, and, where the code under test changes with that option, what each value compiles there;
- how the test is run, as the tree's own files give it: the configuration fragment shipped beside the test and the command its documentation or its Makefile states.

A case that states the contract more plainly than the walk does is shown as an excerpt, introduced and explained like any other construct. A test written in another language than the page's source excerpts, a shell or Python selftest, is cited by file and line and described, never excerpted. A suite whose cases belong to several subsections is introduced once, with its file, its option and how it is run, where its first case appears, and each later subsection names its own cases.

The page covers the tests its scope names and those it finds calling the code it walks. It states no absence of tests: that nothing tests a piece of code is a claim about the whole tree, user-space programs included, which a search for callers does not establish.

A page whose subject is itself a test framework walks the framework as its mechanism: the fixtures, the mock devices, the helpers, the parameter generators, the registration of suites and the runner, with the code under test named as the seam.
