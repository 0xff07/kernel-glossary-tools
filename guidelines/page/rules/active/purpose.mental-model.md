---
qa: off
---

# Mental model

Every DETAILS subsection says what its subject is for before it shows code: the problem the object, mechanism or helper solves, the role it plays in the mechanism the page traces, and the model of objects, relationships and states the reader holds while reading the excerpts.

An opening that names an object and its members, or a helper and its callers, without saying why the kernel keeps that object or performs that operation fails this rule, and so does a subsection that catalogs members, flags or helpers one after another, each with a phrase of what it holds or does and nothing about what the set is for.

A member is explained by the question it answers for the code that reads it, a helper by the situation that needs it, a flag by the decision it steers; a page that reads a definition member by member in declaration order, or a file function by function, has listed the code and explained nothing.

The model names its objects by their relationships: which object owns, points at, contains or is created from which, which one the reader is following, and how the kernel's objects correspond to the terms of the subsystem's specification.

Where the vocabulary and the structures do not map one to one (a bridge, a port and a bus; a host bridge and a root bus; a function and a device; a slot and a device), the page says which kernel object stands for which term, where they coincide and where they differ, before it uses the terms; a term used in two senses without that statement is a finding.

A page about an object states that correspondence once, near its model figure, and every later subsection uses the settled names.

Read the prose of every subsection before its first excerpt for the purpose and the model, and every member or helper explanation for the question it answers. A subsection whose purpose an earlier subsection established carries the result forward in a sentence naming the object and its current state rather than restating the whole mechanism; a subsection that opens on a count, on a list of members or on a helper's name alone is a finding.
