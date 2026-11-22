
void *__kmalloc_flags_noprof(DECL_TOKEN_PARAMS(size, token), gfp_t flags,
				  unsigned int alloc_flags, int node)
				  __assume_kmalloc_alignment __alloc_size(1);

static __always_inline __alloc_size(1) void *_kmalloc_flags_noprof(size_t size,
		gfp_t flags, unsigned int alloc_flags, int node, kmalloc_token_t token)
{
	return __kmalloc_flags_noprof(PASS_TOKEN_PARAMS(size, token), flags, alloc_flags, node);
}
#define kmalloc_flags_noprof(...)	_kmalloc_flags_noprof(__VA_ARGS__, __kmalloc_token(__VA_ARGS__))
#define kmalloc_flags(...)		alloc_hooks(kmalloc_flags_noprof(__VA_ARGS__))

#ifdef CONFIG_64BIT
# ifdef system_has_cmpxchg128
# define system_has_freelist_aba()	system_has_cmpxchg128()
# define try_cmpxchg_freelist		try_cmpxchg128
# endif
typedef u128 freelist_full_t;
#else /* CONFIG_64BIT */
#endif /* CONFIG_64BIT */
